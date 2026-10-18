import { byTime, contactLabel } from "./contact-label";
import { t } from "./i18n.ts";
import { privateReadDenied } from "./read-cache";
import { useStableState as useState } from "./useStableState";
import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  allPages,
  workspaceApi,
  type Detail,
  type Message,
  type Order,
} from "./workspace-api";
import type { components } from "./generated/api";
import type { Features } from "./features";
import { orderCommands, type CreateOrderInput } from "./order-command-api";
import { fieldNames, fieldValue, orderStates } from "./work-order-view";
type Conversation = components["schemas"]["Conversation"];
export function OrderCreation({
  csrf,
  accountId,
  features,
  onSessionExpired,
  onBusyChange,
  onOpenOrder,
  initialConversation = "",
}: {
  csrf: string;
  accountId: string;
  features: Features;
  onSessionExpired: () => void;
  onBusyChange: (b: boolean) => void;
  onOpenOrder: (id: string) => void;
  initialConversation?: string;
}) {
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const api = useMemo(() => workspaceApi(csrf), [csrf]),
    commands = useMemo(() => orderCommands(csrf, accountId), [csrf, accountId]);
  const [suggestions, setSuggestions] = useState<
      components["schemas"]["NewOrderSuggestionView"][]
    >([]),
    [proposalId, setProposalId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]),
    [conversation, setConversation] = useState(initialConversation),
    [messages, setMessages] = useState<Message[]>([]),
    [orders, setOrders] = useState<Order[]>([]),
    [context, setContext] = useState(0),
    [summary, setSummary] = useState(""),
    [scheduleKind, setScheduleKind] = useState("missing"),
    [date, setDate] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [address, setAddress] = useState(""),
    [scheduleSources, setScheduleSources] = useState<string[]>([]),
    [addressSources, setAddressSources] = useState<string[]>([]),
    [additional, setAdditional] = useState(false),
    [review, setReview] = useState(""),
    [consent, setConsent] = useState(false),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [refreshKey, setRefreshKey] = useState(0);
  // Throw the current draft away: nothing is saved, no field has to be filled.
  const resetDraft = (keepConversation = true) => {
    setProposalId("");
    if (!keepConversation) setConversation("");
    setSummary("");
    setAddress("");
    setScheduleKind("missing");
    setStart("");
    setEnd("");
    setDate("");
    setAddressSources([]);
    setScheduleSources([]);
    setAdditional(false);
    setReview("");
    setConsent(false);
  };
  const dismissSuggestion = async (
    s: components["schemas"]["NewOrderSuggestionView"],
  ) => {
    setBusy(true);
    setError("");
    try {
      await api(`/new-order-suggestions/${s.id}/dismiss`, {
        expected_context_version: s.context_version,
      });
      if (proposalId === s.id) resetDraft();
      setRefreshKey((v) => v + 1);
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  const report = useCallback(
    (e: unknown) => {
      setError(e instanceof Error ? e.message : t("读取失败，请刷新。"));
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        onSessionExpired();
    },
    [onSessionExpired],
  );
  useEffect(() => {
    const abort = new AbortController();
    setLoading(!conversations.length);
    setError("");
    void (async () => {
      try {
        const [choices, allOrders, proposed] = await Promise.all([
          allPages<Conversation>(api, "/conversations", abort.signal),
          allPages<Order>(api, "/work-orders", abort.signal),
          features.business_loop_reviewed
            ? allPages<components["schemas"]["NewOrderSuggestionView"]>(
                api,
                "/new-order-suggestions",
                abort.signal,
              )
            : Promise.resolve([]),
        ]);
        if (abort.signal.aborted) return;
        setSuggestions(proposed);
        setConversations(choices);
        setOrders(allOrders);
        if (conversation) {
          const [info, texts] = await Promise.all([
            api<Detail<Conversation>>(
              `/conversations/${conversation}`,
              undefined,
              abort.signal,
            ),
            allPages<Message>(
              api,
              `/conversations/${conversation}/messages`,
              abort.signal,
            ),
          ]);
          if (abort.signal.aborted) return;
          if (
            info.data.id !== conversation ||
            info.data.account_id !== accountId ||
            texts.some((m) => m.conversation_id !== conversation)
          )
            throw new Error(t("会话归属无法核对，不能建单。"));
          setContext(info.data.context_version);
          setMessages([...texts].sort(byTime<Message>((m) => m.occurred_at)));
        }
      } catch (e) {
        if (!abort.signal.aborted) {
          setReview("");
          setConsent(false);
          if (privateReadDenied(e)) {
            setConversations([]);
            setOrders([]);
            setMessages([]);
            setContext(0);
          }
          report(e);
        }
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    })();
    return () => abort.abort();
  }, [api, conversation, accountId, report, refreshKey]);
  const eligible = messages.filter(
    (m) =>
      m.direction === "incoming" &&
      m.source !== "api" &&
      !m.revoked &&
      m.text !== null &&
      !messages.some(
        (other) => other.id === m.id && other.revision > m.revision,
      ),
  );
  const open = orders.filter(
    (o) =>
      o.conversation_ids.includes(conversation) &&
      !["completed", "cancelled"].includes(o.status),
  );
  const refs = (ids: string[]) =>
    ids
      .map((id) => eligible.find((m) => m.id === id))
      .filter((m): m is Message => !!m)
      .map((m) => ({ message_id: m.id, message_revision: m.revision }));
  const problem = loading
    ? t("正在核对会话与来源。")
    : !conversation || !context
      ? t("请选择可用的已授权会话。")
      : !summary.trim() || summary.trim().length > 120
        ? t("请填写 1–120 字的业务摘要。")
        : scheduleKind !== "missing" && !scheduleSources.length
          ? t("有时间时，必须选择客户说明时间的原文。")
          : scheduleKind === "date_only" && !date
            ? t("请选择日期。")
            : scheduleKind === "timed" &&
                (!start ||
                  !end ||
                  Date.parse(start + "+08:00") <= Date.now() ||
                  Date.parse(end + "+08:00") <= Date.parse(start + "+08:00"))
              ? t("请填写未来的开始时间和更晚的结束时间。")
              : address && !address.trim()
                ? t("地址不能只有空格。")
                : address.trim() && !addressSources.length
                  ? t("有地址时，必须选择客户说明地址的原文。")
                  : open.length && !additional
                    ? t("已有未结束工单；另开一单需要明确确认。")
                    : "";
  let body: CreateOrderInput | null = null;
  if (!problem)
    body = {
      conversation_id: conversation,
      summary: summary.trim(),
      schedule:
        scheduleKind === "missing"
          ? null
          : scheduleKind === "date_only"
            ? { kind: "date_only", date, timezone: "Asia/Hong_Kong" }
            : {
                kind: "timed",
                start_at: new Date(start + "+08:00").toISOString(),
                end_at: new Date(end + "+08:00").toISOString(),
                timezone: "Asia/Hong_Kong",
              },
      schedule_sources: scheduleKind === "missing" ? [] : refs(scheduleSources),
      address: address.trim() || null,
      address_sources: address.trim() ? refs(addressSources) : [],
      confirm_additional_order: additional,
      ...(proposalId
        ? { from_proposal_id: proposalId, expected_context_version: context }
        : {}),
    };
  const binding = JSON.stringify({ body, context, messages: eligible }),
    reviewCurrent = !!review && review === binding;
  async function submit() {
    if (
      !features.create_order ||
      !reviewCurrent ||
      !consent ||
      !body ||
      busy ||
      loading
    )
      return;
    setBusy(true);
    onBusyChange(true);
    try {
      const order = await commands.submit({ kind: "create", body });
      if (active.current) onOpenOrder(order.id);
    } catch (e) {
      if (!active.current) return;
      report(e);
      setReview("");
      setConsent(false);
    } finally {
      if (active.current) {
        setBusy(false);
        onBusyChange(false);
      }
    }
  }
  function choose(id: string, type: "schedule" | "address") {
    const setter = type === "schedule" ? setScheduleSources : setAddressSources;
    setter((values) =>
      values.includes(id) ? values.filter((v) => v !== id) : [...values, id],
    );
    setConsent(false);
  }
  return (
    <section aria-label={t("从会话新建工单")}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t("新客户到第一张工单")}</p>
          <h1>{t("从会话新建工单")}</h1>
          <p>
            {t("只引用客户原文；不知道的时间和地址保持未提供，不自动编造。")}
          </p>
        </div>
        <button
          className="secondary"
          disabled={loading || busy}
          onClick={() => setRefreshKey((v) => v + 1)}
        >
          {t("刷新会话与原文")}
        </button>
      </div>
      {!features.create_order && (
        <p className="notice warning">
          {t(
            "当前连接的后端未开放建单功能。下面可以填写和核对，提交按钮保持关闭。",
          )}
        </p>
      )}
      {error && (
        <p className="notice stale" role="alert">
          {t(error)}
        </p>
      )}
      {commands.error && <p role="alert">{t(commands.error)}</p>}
      {commands.attempt && (
        <p className="notice warning">
          {t("有尚待核对的原操作")}
          {commands.attempt.key}
          {t("，不能另开新请求。请到业务工作台核对原操作。")}
        </p>
      )}
      {features.business_loop_reviewed && (
        <section className="panel" data-tour="create-suggestions">
          <h2>{t("AI 新单建议")}</h2>
          <p>
            {t(
              "建议不会自动建单。选择后只预填摘要；时间、地址仍需逐项核对客户原文并明确填写。",
            )}
          </p>
          {!suggestions.length && (
            <p>{t("目前没有待核对的新单建议；你可以直接手动建单。")}</p>
          )}
          {suggestions.map((s) => (
            <article key={s.id}>
              <h3>{s.suggestion.summary}</h3>
              {s.suggestion.fields.map((f, i) => (
                <p key={i}>
                  {fieldNames[f.field] ?? f.field}：{fieldValue(f.value)}
                </p>
              ))}
              {s.suggestion.unresolved_questions.map((q, i) => (
                <p key={i}>{q}</p>
              ))}
              <button
                type="button"
                className="secondary"
                disabled={busy || loading}
                onClick={() => {
                  setProposalId(s.id);
                  setConversation(s.conversation_id);
                  setSummary(s.suggestion.summary.slice(0, 120));
                  setAddress("");
                  setScheduleKind("missing");
                  setStart("");
                  setEnd("");
                  setDate("");
                  setAddressSources([]);
                  setScheduleSources([]);
                  setAdditional(false);
                  setReview("");
                  setConsent(false);
                }}
              >
                {t("核对这份新单建议")}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={busy || loading}
                onClick={() => void dismissSuggestion(s)}
              >
                {t("不是新单，忽略这条建议")}
              </button>
            </article>
          ))}
          {proposalId && (
            <p role="status">
              {t("已选择建议")}
              {t("；提交时会重新核对来源与版本。")}
            </p>
          )}
        </section>
      )}
      <div className="planning-grid">
        <form
          className="panel"
          onSubmit={(e) => {
            e.preventDefault();
            if (body) {
              setReview(binding);
              setConsent(false);
            }
          }}
        >
          <label>
            {t("已授权会话")}
            <select
              value={conversation}
              disabled={busy || loading}
              onChange={(e) => {
                setProposalId("");
                setConversation(e.target.value);
                setSummary("");
                setAddress("");
                setScheduleKind("missing");
                setStart("");
                setEnd("");
                setDate("");
              }}
            >
              <option value="">{t("请选择会话")}</option>
              {conversations.map((c) => (
                <option key={c.id} value={c.id}>
                  {contactLabel(c.provider_conversation_id)} {t("· 已关联")}
                  {c.work_order_ids.length} {t("张工单")}
                </option>
              ))}
            </select>
          </label>
          {!loading && !conversations.length && (
            <p>{t("暂无已授权会话，请先在 WhatsApp 连接页选择聊天。")}</p>
          )}
          {open.length > 0 && (
            <div className="notice">
              <p>{t("该会话已有未结束工单：")}</p>
              {open.map((o) => (
                <p key={o.id}>
                  {o.summary} · {orderStates[o.status]}{" "}
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => onOpenOrder(o.id)}
                  >
                    {t("查看已有工单")}
                  </button>
                </p>
              ))}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={additional}
                  onChange={(e) => setAdditional(e.target.checked)}
                />
                {t("这是另一项业务，我确认另开一张工单")}
              </label>
            </div>
          )}
          <label>
            {t("业务摘要")}
            <input
              value={summary}
              maxLength={120}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={t("客户称呼和具体工作")}
              disabled={busy}
            />
          </label>
          <label>
            {t("时间信息")}
            <select
              value={scheduleKind}
              onChange={(e) => setScheduleKind(e.target.value)}
              disabled={busy}
            >
              <option value="missing">{t("尚未提供")}</option>
              <option value="date_only">{t("只知道日期，时间待确认")}</option>
              <option value="timed">{t("具体开始和结束时间")}</option>
            </select>
          </label>
          {scheduleKind === "date_only" && (
            <label>
              {t("日期")}
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
          )}
          {scheduleKind === "timed" && (
            <>
              <label>
                {t("开始（香港时间）")}
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </label>
              <label>
                {t("结束（香港时间）")}
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </label>
            </>
          )}
          <label>
            {t("客户提供的地址（可留空）")}
            <input
              value={address}
              maxLength={300}
              onChange={(e) => setAddress(e.target.value)}
              disabled={busy}
            />
          </label>
          <p className="subtle">
            {t(
              "仅日期仍属暂定。填了时间或地址，也必须核对客户在哪条消息中说明；商户自己的消息不能代替客户确认。",
            )}
          </p>
          {problem && <p role="status">{problem}</p>}
          <button
            disabled={
              !!problem || busy || !!commands.error || !!commands.attempt
            }
          >
            {t("核对新工单")}
          </button>
          {(proposalId ||
            summary ||
            address ||
            scheduleKind !== "missing" ||
            review) && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => resetDraft()}
            >
              {t("放弃这份草稿")}
            </button>
          )}
          {review && (
            <section className="review-panel" aria-label={t("新工单复核")}>
              <h2>{t("核对后再保存")}</h2>
              {reviewCurrent && body ? (
                <>
                  <p>{body.summary}</p>
                  <p>
                    {t("时间：")}
                    {fieldValue(body.schedule)}
                  </p>
                  <p>
                    {t("地址：")}
                    {body.address ?? t("未提供，等待客户说明")}
                  </p>
                  <small>
                    {t("来源会话 v")}
                    {context} {t("· 时间原文")} {body.schedule_sources.length}{" "}
                    {t("条 · 地址原文")} {body.address_sources.length} {t("条")}
                  </small>
                </>
              ) : (
                <p>{t("内容或来源已变化，请重新核对。")}</p>
              )}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={!reviewCurrent || busy}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                {t("我已核对摘要、时间、地址和客户来源；缺项保持待确认")}
              </label>
              <button
                type="button"
                disabled={
                  !features.create_order || !reviewCurrent || !consent || busy
                }
                onClick={() => void submit()}
              >
                {t("保存新工单")}
              </button>
            </section>
          )}
        </form>
        <aside className="panel">
          <h2>{t("选择客户原文依据")}</h2>
          <small>
            {t(
              "只显示本会话最新、未撤回且有文字的客户消息。历史快照和商户回显不能当成客户确认。",
            )}
          </small>
          {loading && <p>{t("正在读取…")}</p>}
          {eligible.map((m) => (
            <article className="message" key={m.id}>
              <small>
                {t("客户 · r")}
                {m.revision} · {m.occurred_at}
              </small>
              <p>{m.text}</p>
              {scheduleKind !== "missing" && (
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={scheduleSources.includes(m.id)}
                    onChange={() => choose(m.id, "schedule")}
                  />
                  {t("作为时间依据")}
                </label>
              )}
              {address.trim() && (
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={addressSources.includes(m.id)}
                    onChange={() => choose(m.id, "address")}
                  />
                  {t("作为地址依据")}
                </label>
              )}
            </article>
          ))}
          {!loading && !eligible.length && (
            <p>
              {t(
                "没有可用客户原文。可先留空时间／地址，等待客户补充；不能猜测确认。",
              )}
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}
