import { t } from "./i18n.ts";
import { privateReadDenied } from "./read-cache";
import { useStableState as useState } from "./useStableState";
import { useEffect, useMemo } from "react";
import { businessLoopApi } from "./business-loop-api";
import { LoopCommand, LoopRecovery } from "./LoopCommand";
import { loopReady, type Features } from "./features";
import {
  allPages,
  workspaceApi,
  type Message,
  type Order,
  type Change,
} from "./workspace-api";
import type { components } from "./generated/api";
import { fieldNames, fieldValue, reviewReasons } from "./work-order-view";
import {
  byTime,
  contactLabel,
  loadContactLabels,
  shortTime,
} from "./contact-label";
type ReviewItem = components["schemas"]["ReviewItem"];
export function ReviewWorkspace({
  csrf,
  onSessionExpired,
  onOpenOrder,
  onConnect,
  accountId,
  features,
  onBusyChange,
  onCreate,
}: {
  csrf: string;
  onSessionExpired: () => void;
  onOpenOrder: (id: string) => void;
  onConnect: () => void;
  accountId: string;
  features: Features;
  onBusyChange: (busy: boolean) => void;
  onCreate: (conversationId: string) => void;
}) {
  const api = useMemo(() => workspaceApi(csrf), [csrf]);
  const commands = useMemo(
    () => businessLoopApi(csrf, accountId, features),
    [csrf, accountId, features],
  );
  const [target, setTarget] = useState("");
  const [context, setContext] = useState(0);
  const [items, setItems] = useState<ReviewItem[]>([]),
    [orders, setOrders] = useState<Order[]>([]),
    [changes, setChanges] = useState<Change[]>([]),
    [selected, setSelected] = useState<ReviewItem | null>(null),
    [messages, setMessages] = useState<Message[]>([]),
    [error, setError] = useState(""),
    [contextError, setContextError] = useState(""),
    [loading, setLoading] = useState(true),
    [contacts, setContacts] = useState<Map<string, string>>(new Map()),
    [version, setVersion] = useState(0);
  const contact = (conversationId: string) =>
    contacts.get(conversationId) ?? contactLabel(undefined);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(!items.length && !orders.length);
    setError("");

    void (async () => {
      try {
        const [unordered, list, labels] = await Promise.all([
          allPages<ReviewItem>(api, "/review-items", abort.signal),
          allPages<Order>(api, "/work-orders", abort.signal),
          loadContactLabels(api, abort.signal),
        ]);
        // The server pages by id; the queue is shown strictly by arrival time.
        const queue = [...unordered].sort(
          byTime<ReviewItem>((i) => i.observed_at),
        );
        const allChanges = (
          await Promise.all(
            list.map((o) =>
              allPages<Change>(
                api,
                `/work-orders/${o.id}/changes`,
                abort.signal,
              ),
            ),
          )
        ).flat();
        if (!abort.signal.aborted) {
          setSelected((old) =>
            old ? (queue.find((i) => i.id === old.id) ?? null) : null,
          );
          setItems(queue);
          setContacts(labels);
          setOrders(list);
          setChanges(allChanges);
        }
      } catch (e) {
        if (!abort.signal.aborted) {
          if (privateReadDenied(e)) {
            setItems([]);
            setOrders([]);
            setChanges([]);
            setSelected(null);
            setMessages([]);
          }
          setError(e instanceof Error ? e.message : t("复核数据暂不可用"));
          if ((e as { code?: string })?.code === "UNAUTHENTICATED")
            onSessionExpired();
        }
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    })();
    return () => abort.abort();
  }, [api, version, onSessionExpired]);
  useEffect(() => {
    const abort = new AbortController();
    setContextError("");
    setContext(0);
    setMessages([]);
    setTarget("");
    if (selected)
      void Promise.all([
        allPages<Message>(
          api,
          `/conversations/${selected.conversation_id}/messages`,
          abort.signal,
        ),
        api<{ data: components["schemas"]["Conversation"] }>(
          `/conversations/${selected.conversation_id}`,
          undefined,
          abort.signal,
        ),
      ])
        .then(([values, info]) => {
          if (!abort.signal.aborted) {
            if (
              info.data.id !== selected.conversation_id ||
              info.data.account_id !== accountId ||
              values.some((m) => m.conversation_id !== selected.conversation_id)
            )
              throw new Error(t("来源会话无法核对。"));
            setMessages(
              [...values].sort(byTime<Message>((m) => m.occurred_at)),
            );
            setContext(info.data.context_version);
          }
        })
        .catch((e) => {
          if (!abort.signal.aborted) {
            setContextError(e instanceof Error ? e.message : t("原文无法读取"));
            if (e?.code === "UNAUTHENTICATED") onSessionExpired();
          }
        });
    return () => abort.abort();
  }, [
    api,
    accountId,
    selected?.id,
    selected?.current_context_version,
    version,
    onSessionExpired,
  ]);
  const done = () => setVersion((v) => v + 1);
  const report = (e: unknown) => {
    setError(e instanceof Error ? e.message : t("复核数据暂不可用"));
    if ((e as { code?: string })?.code === "UNAUTHENTICATED")
      onSessionExpired();
  };
  const current =
    !!selected &&
    !loading &&
    !error &&
    !contextError &&
    context === selected.context_version &&
    context === selected.current_context_version &&
    selected.state === "completed" &&
    [
      "ASSIGNMENT_NEEDS_REVIEW",
      "EXTRACTION_NEEDS_REVIEW",
      "MODEL_OUTCOME_UNKNOWN",
    ].includes(selected.reason) &&
    messages.some((m) => m.id === selected.message_id && !m.revoked);
  const openOrders = orders.filter(
    (o) =>
      selected &&
      o.conversation_ids.includes(selected.conversation_id) &&
      !["completed", "cancelled"].includes(o.status),
  );
  return (
    <section aria-label={t("人工复核")}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t("需要你判断")}</p>
          <h1>{t("人工复核")}</h1>
          <p>
            {t(
              "把没有理解、没有归单和来源失效的问题摆出来。不会自动接受、重发或改写工单。",
            )}
          </p>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => setVersion((v) => v + 1)}
        >
          {t("刷新复核事项")}
        </button>
      </div>
      {error && (
        <p role="alert" className="notice stale">
          {t(error)}
        </p>
      )}
      {loading && <p role="status">{t("正在读取复核事项…")}</p>}
      <LoopRecovery
        api={commands}
        onDone={done}
        onError={report}
        onBusy={onBusyChange}
      />
      <div className="planning-grid">
        <div className="panel">
          <h2>{t("消息处理待核对")}</h2>
          <small>
            {t(
              "这是处理记录，可能包含旧轮次；查看最新原文后再判断，不能把旧诊断当成当前失败。",
            )}
          </small>
          {items.map((item) => (
            <article className="review-item" key={item.id}>
              <h3>
                {item.reason === "PROCESSING_FAILED" &&
                ["pending", "processing"].includes(item.state)
                  ? t("处理暂未完成，系统正在自动重试")
                  : (reviewReasons[item.reason] ?? t("需要人工核对"))}
              </h3>
              <small>
                {contact(item.conversation_id)} · {shortTime(item.observed_at)}{" "}
                {t("· 记录 v")}
                {item.context_version} {t("/ 当前 v")}
                {item.current_context_version}
                {item.context_version !== item.current_context_version
                  ? t(" · 历史轮次")
                  : ""}
              </small>
              <button
                className="secondary"
                aria-pressed={selected?.id === item.id}
                onClick={() => {
                  if (selected?.conversation_id !== item.conversation_id)
                    setMessages([]);
                  setSelected(item);
                }}
              >
                {t("查看这条会话原文")}
              </button>
            </article>
          ))}
          {!loading && !error && !items.length && (
            <p>
              {t(
                "目前没有记录到需复核的处理事项。这不表示 AI 已理解所有聊天。",
              )}
            </p>
          )}
          {selected && (
            <section className="review-panel">
              <h3>
                {t("来源会话")} {contact(selected.conversation_id)}
              </h3>
              {contextError && <p role="alert">{contextError}</p>}
              {messages.map((m) => (
                <article className="message" key={m.id}>
                  <small>
                    {m.direction === "incoming" ? t("客户") : t("商户")} ·{" "}
                    {shortTime(m.occurred_at)} · r{m.revision}
                    {m.id === selected.message_id ? t(" · 触发消息") : ""}
                  </small>
                  <p>
                    {m.revoked
                      ? t("已撤回，不可用于确认")
                      : (m.text ?? t("无可读取文字，请核对附件"))}
                  </p>
                </article>
              ))}
              {!messages.length && !contextError && (
                <p>{t("尚无可读取原文。")}</p>
              )}
              <h3>{t("该会话已有工单")}</h3>
              {!openOrders.length && (
                <p>{t("这条会话没有开放工单。新需求可以从这里手动建单。")}</p>
              )}
              {orders
                .filter((o) =>
                  o.conversation_ids.includes(selected.conversation_id),
                )
                .map((o) => (
                  <button
                    key={o.id}
                    className="secondary"
                    onClick={() => onOpenOrder(o.id)}
                  >
                    {o.summary}
                  </button>
                ))}
              {features.create_order && !contextError && context > 0 && (
                <button
                  className="secondary"
                  onClick={() => onCreate(selected.conversation_id)}
                >
                  {t("为这条会话新建工单")}
                </button>
              )}
              {features.manual_assignment && loopReady(features) && (
                <div className="review-decisions">
                  <h3>{t("处理这条消息")}</h3>
                  <p>
                    {t(
                      "归单会重新生成待核对提议；忽略只表示这条消息无需处理。手动建单不会自动清除此复核事项。",
                    )}
                  </p>
                  {!current && (
                    <p role="status">
                      {t(
                        "这条记录不是当前可处理轮次，或原文尚未核实。请刷新并处理最新记录。",
                      )}
                    </p>
                  )}
                  {selected.reason === "MODEL_OUTCOME_UNKNOWN" && (
                    <p>
                      {t(
                        "模型调用结果未知，只能核查原请求或明确忽略，不能重新归单调用。",
                      )}
                    </p>
                  )}
                  <label>
                    {t("归入工单")}
                    <select
                      value={target}
                      onChange={(e) => setTarget(e.target.value)}
                      disabled={!current}
                    >
                      <option value="">{t("选择已有开放工单")}</option>
                      {openOrders.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.summary}
                        </option>
                      ))}
                    </select>
                  </label>
                  {target && selected.reason !== "MODEL_OUTCOME_UNKNOWN" && (
                    <LoopCommand
                      key={selected.id + target}
                      api={commands}
                      disabled={
                        !current || !openOrders.some((o) => o.id === target)
                      }
                      label={t("核对归单")}
                      onDone={done}
                      onError={report}
                      onBusy={onBusyChange}
                      intent={{
                        path: `/review-items/${selected.id}/assign`,
                        body: {
                          action: "assign",
                          expected_context_version: context,
                          work_order_id: target,
                        },
                        review: t(
                          "将当前会话 v{0} 的这条消息归入“{1}”，仅记录归属，不自动确认业务字段。",
                          context,
                          openOrders.find((o) => o.id === target)?.summary,
                        ),
                      }}
                    />
                  )}
                  <LoopCommand
                    key={selected.id + ":dismiss"}
                    api={commands}
                    disabled={!current}
                    label={t("标记无需归单")}
                    onDone={done}
                    onError={report}
                    onBusy={onBusyChange}
                    intent={{
                      path: `/review-items/${selected.id}/assign`,
                      body: {
                        action: "dismiss",
                        expected_context_version: context,
                        work_order_id: null,
                      },
                      review: t(
                        "将当前会话 v{0} 的这条消息标记为无需归单，不创建工单，不发送回复。",
                        context,
                      ),
                    }}
                  />
                </div>
              )}
            </section>
          )}
        </div>
        <aside className="panel">
          <h2>{t("工单缺项与含糊回复")}</h2>
          {orders
            .filter((o) => !["completed", "cancelled"].includes(o.status))
            .filter(
              (o) =>
                Object.values(o.fields).some((f) => f.status !== "confirmed") ||
                changes.some(
                  (c) =>
                    c.work_order_id === o.id &&
                    ["proposed", "needs_review"].includes(c.status),
                ),
            )
            .map((o) => (
              <article className="review-item" key={o.id}>
                <h3>{o.summary}</h3>
                {Object.entries(o.fields)
                  .filter(([, f]) => f.status !== "confirmed")
                  .map(([key, f]) => (
                    <p key={key}>
                      {fieldNames[key as keyof typeof fieldNames] ?? key}：
                      {fieldValue(f.value)} ·{" "}
                      {f.status === "missing"
                        ? t("等待客户提供")
                        : f.status === "needs_review"
                          ? t("原文或含义需要复核")
                          : t("等待客户核实和商户确认")}
                    </p>
                  ))}
                {changes
                  .filter(
                    (c) =>
                      c.work_order_id === o.id &&
                      ["proposed", "needs_review"].includes(c.status),
                  )
                  .map((c) => (
                    <p key={c.id}>
                      {fieldNames[c.field]}：
                      {c.customer_confirmation === "ambiguous"
                        ? t("客户回复含糊，不能默认同意")
                        : c.customer_confirmation === "confirmed"
                          ? t("客户已确认，等待商户核对")
                          : t("客户尚未明确确认")}
                    </p>
                  ))}
                <button className="secondary" onClick={() => onOpenOrder(o.id)}>
                  {t("核对工单和来源")}
                </button>
              </article>
            ))}
          <h2>{t("附件与部分结果")}</h2>
          <p>
            {t(
              "到 WhatsApp 消息页查看附件、部分文字、来源版本和人工确认。处理失败或结果未知不会自动重发；扫描 PDF 的文字识别和真实语音理解仍未交付。",
            )}
          </p>
          <button className="secondary" onClick={onConnect}>
            {t("前往消息与附件")}
          </button>
        </aside>
      </div>
    </section>
  );
}
