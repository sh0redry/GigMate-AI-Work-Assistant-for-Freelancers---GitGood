import { useCallback, useEffect, useMemo, useState, useRef } from "react";
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
import { fieldValue, orderStates } from "./work-order-view";
type Conversation = components["schemas"]["Conversation"];
export function OrderCreation({
  csrf,
  accountId,
  features,
  onSessionExpired,
  onBusyChange,
  onOpenOrder,
}: {
  csrf: string;
  accountId: string;
  features: Features;
  onSessionExpired: () => void;
  onBusyChange: (b: boolean) => void;
  onOpenOrder: (id: string) => void;
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
  const [conversations, setConversations] = useState<Conversation[]>([]),
    [conversation, setConversation] = useState(""),
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
  const report = useCallback(
    (e: unknown) => {
      setError(e instanceof Error ? e.message : "读取失败，请刷新。");
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        onSessionExpired();
    },
    [onSessionExpired],
  );
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setReview("");
    setConsent(false);
    setMessages([]);
    setContext(0);
    setScheduleSources([]);
    setAddressSources([]);
    setAdditional(false);
    setError("");
    void (async () => {
      try {
        const [choices, allOrders] = await Promise.all([
          allPages<Conversation>(api, "/conversations", abort.signal),
          allPages<Order>(api, "/work-orders", abort.signal),
        ]);
        if (abort.signal.aborted) return;
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
            throw new Error("会话归属无法核对，不能建单。");
          setContext(info.data.context_version);
          setMessages(texts);
        }
      } catch (e) {
        if (!abort.signal.aborted) {
          setConversations([]);
          setOrders([]);
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
    ? "正在核对会话与来源。"
    : !conversation || !context
      ? "请选择可用的已授权会话。"
      : !summary.trim() || summary.trim().length > 120
        ? "请填写 1–120 字的业务摘要。"
        : scheduleKind !== "missing" && !scheduleSources.length
          ? "有时间时，必须选择客户说明时间的原文。"
          : scheduleKind === "date_only" && !date
            ? "请选择日期。"
            : scheduleKind === "timed" &&
                (!start ||
                  !end ||
                  Date.parse(start + "+08:00") <= Date.now() ||
                  Date.parse(end + "+08:00") <= Date.parse(start + "+08:00"))
              ? "请填写未来的开始时间和更晚的结束时间。"
              : address && !address.trim()
                ? "地址不能只有空格。"
                : address.trim() && !addressSources.length
                  ? "有地址时，必须选择客户说明地址的原文。"
                  : open.length && !additional
                    ? "已有未结束工单；另开一单需要明确确认。"
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
    <section aria-label="从会话新建工单">
      <div className="page-heading">
        <div>
          <p className="eyebrow">新客户到第一张工单</p>
          <h1>从会话新建工单</h1>
          <p>只引用客户原文；不知道的时间和地址保持未提供，不自动编造。</p>
        </div>
        <button
          className="secondary"
          disabled={loading || busy}
          onClick={() => setRefreshKey((v) => v + 1)}
        >
          刷新会话与原文
        </button>
      </div>
      {!features.create_order && (
        <p className="notice warning">
          当前连接的后端未开放建单功能。下面可以填写和核对，提交按钮保持关闭。
        </p>
      )}
      {error && (
        <p className="notice stale" role="alert">
          {error}
        </p>
      )}
      {commands.error && <p role="alert">{commands.error}</p>}
      {commands.attempt && (
        <p className="notice warning">
          有尚待核对的原操作 {commands.attempt.key}
          ，不能另开新请求。请到业务工作台核对原操作。
        </p>
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
            已授权会话
            <select
              value={conversation}
              disabled={busy || loading}
              onChange={(e) => {
                setConversation(e.target.value);
                setSummary("");
                setAddress("");
                setScheduleKind("missing");
                setStart("");
                setEnd("");
                setDate("");
              }}
            >
              <option value="">请选择会话</option>
              {conversations.map((c) => (
                <option key={c.id} value={c.id}>
                  会话 {c.id.slice(-6)} · 已关联 {c.work_order_ids.length}{" "}
                  张工单
                </option>
              ))}
            </select>
          </label>
          {!loading && !conversations.length && (
            <p>暂无已授权会话，请先在 WhatsApp 连接页选择聊天。</p>
          )}
          {open.length > 0 && (
            <div className="notice">
              <p>该会话已有未结束工单：</p>
              {open.map((o) => (
                <p key={o.id}>
                  {o.summary} · {orderStates[o.status]}{" "}
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => onOpenOrder(o.id)}
                  >
                    查看已有工单
                  </button>
                </p>
              ))}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={additional}
                  onChange={(e) => setAdditional(e.target.checked)}
                />
                这是另一项业务，我确认另开一张工单
              </label>
            </div>
          )}
          <label>
            业务摘要
            <input
              value={summary}
              maxLength={120}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="客户称呼和具体工作"
              disabled={busy}
            />
          </label>
          <label>
            时间信息
            <select
              value={scheduleKind}
              onChange={(e) => setScheduleKind(e.target.value)}
              disabled={busy}
            >
              <option value="missing">尚未提供</option>
              <option value="date_only">只知道日期，时间待确认</option>
              <option value="timed">具体开始和结束时间</option>
            </select>
          </label>
          {scheduleKind === "date_only" && (
            <label>
              日期
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
                开始（香港时间）
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </label>
              <label>
                结束（香港时间）
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </label>
            </>
          )}
          <label>
            客户提供的地址（可留空）
            <input
              value={address}
              maxLength={300}
              onChange={(e) => setAddress(e.target.value)}
              disabled={busy}
            />
          </label>
          <p className="subtle">
            仅日期仍属暂定。填了时间或地址，也必须核对客户在哪条消息中说明；商户自己的消息不能代替客户确认。
          </p>
          {problem && <p role="status">{problem}</p>}
          <button
            disabled={
              !!problem || busy || !!commands.error || !!commands.attempt
            }
          >
            核对新工单
          </button>
          {review && (
            <section className="review-panel" aria-label="新工单复核">
              <h2>核对后再保存</h2>
              {reviewCurrent && body ? (
                <>
                  <p>{body.summary}</p>
                  <p>时间：{fieldValue(body.schedule)}</p>
                  <p>地址：{body.address ?? "未提供，等待客户说明"}</p>
                  <small>
                    来源会话 v{context} · 时间原文{" "}
                    {body.schedule_sources.length} 条 · 地址原文{" "}
                    {body.address_sources.length} 条
                  </small>
                </>
              ) : (
                <p>内容或来源已变化，请重新核对。</p>
              )}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={!reviewCurrent || busy}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                我已核对摘要、时间、地址和客户来源；缺项保持待确认
              </label>
              <button
                type="button"
                disabled={
                  !features.create_order || !reviewCurrent || !consent || busy
                }
                onClick={() => void submit()}
              >
                保存新工单
              </button>
            </section>
          )}
        </form>
        <aside className="panel">
          <h2>选择客户原文依据</h2>
          <small>
            只显示本会话最新、未撤回且有文字的客户消息。历史快照和商户回显不能当成客户确认。
          </small>
          {loading && <p>正在读取…</p>}
          {eligible.map((m) => (
            <article className="message" key={m.id}>
              <small>
                客户 · r{m.revision} · {m.occurred_at}
              </small>
              <p>{m.text}</p>
              {scheduleKind !== "missing" && (
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={scheduleSources.includes(m.id)}
                    onChange={() => choose(m.id, "schedule")}
                  />
                  作为时间依据
                </label>
              )}
              {address.trim() && (
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={addressSources.includes(m.id)}
                    onChange={() => choose(m.id, "address")}
                  />
                  作为地址依据
                </label>
              )}
            </article>
          ))}
          {!loading && !eligible.length && (
            <p>
              没有可用客户原文。可先留空时间／地址，等待客户补充；不能猜测确认。
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}
