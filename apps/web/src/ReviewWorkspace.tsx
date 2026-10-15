import { useEffect, useMemo, useState } from "react";
import {
  allPages,
  workspaceApi,
  type Message,
  type Order,
  type Change,
} from "./workspace-api";
import type { components } from "./generated/api";
import { fieldNames, fieldValue } from "./work-order-view";
type ReviewItem = components["schemas"]["ReviewItem"];
const reasons: Record<string, string> = {
  LIVE_EXTRACTION_PENDING: "真实消息理解尚未启用",
  EXTRACTION_NEEDS_REVIEW: "模型未能确定业务含义，需要人工核对",
  ASSIGNMENT_NEEDS_REVIEW: "无法确定属于哪张工单",
  PROCESSING_FAILED: "处理失败，需要核对原文",
  RETRY_EXHAUSTED: "多次处理未完成，需要人工核对",
};
export function ReviewWorkspace({
  csrf,
  onSessionExpired,
  onOpenOrder,
  onConnect,
}: {
  csrf: string;
  onSessionExpired: () => void;
  onOpenOrder: (id: string) => void;
  onConnect: () => void;
}) {
  const api = useMemo(() => workspaceApi(csrf), [csrf]);
  const [items, setItems] = useState<ReviewItem[]>([]),
    [orders, setOrders] = useState<Order[]>([]),
    [changes, setChanges] = useState<Change[]>([]),
    [selected, setSelected] = useState<ReviewItem | null>(null),
    [messages, setMessages] = useState<Message[]>([]),
    [error, setError] = useState(""),
    [contextError, setContextError] = useState(""),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError("");
    setSelected(null);
    setMessages([]);
    void (async () => {
      try {
        const [queue, list] = await Promise.all([
          allPages<ReviewItem>(api, "/review-items", abort.signal),
          allPages<Order>(api, "/work-orders", abort.signal),
        ]);
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
          setItems(queue);
          setOrders(list);
          setChanges(allChanges);
        }
      } catch (e) {
        if (!abort.signal.aborted) {
          setItems([]);
          setOrders([]);
          setChanges([]);
          setError(e instanceof Error ? e.message : "复核数据暂不可用");
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
    setMessages([]);
    setContextError("");
    if (selected)
      void allPages<Message>(
        api,
        `/conversations/${selected.conversation_id}/messages`,
        abort.signal,
      )
        .then((values) => {
          if (!abort.signal.aborted) {
            if (
              values.some((m) => m.conversation_id !== selected.conversation_id)
            )
              throw new Error("来源会话无法核对。");
            setMessages(values);
          }
        })
        .catch((e) => {
          if (!abort.signal.aborted) {
            setContextError(e instanceof Error ? e.message : "原文无法读取");
            if (e?.code === "UNAUTHENTICATED") onSessionExpired();
          }
        });
    return () => abort.abort();
  }, [api, selected, onSessionExpired]);
  return (
    <section aria-label="人工复核">
      <div className="page-heading">
        <div>
          <p className="eyebrow">需要你判断</p>
          <h1>人工复核</h1>
          <p>
            把没有理解、没有归单和来源失效的问题摆出来。不会自动接受、重发或改写工单。
          </p>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => setVersion((v) => v + 1)}
        >
          刷新复核事项
        </button>
      </div>
      {error && (
        <p role="alert" className="notice stale">
          {error}
        </p>
      )}
      {loading && <p role="status">正在读取复核事项…</p>}
      <div className="planning-grid">
        <div className="panel">
          <h2>消息处理待核对</h2>
          <small>
            这是处理记录，可能包含旧轮次；查看最新原文后再判断，不能把旧诊断当成当前失败。
          </small>
          {items.map((item) => (
            <article className="review-item" key={item.id}>
              <h3>{reasons[item.reason] ?? "需要人工核对"}</h3>
              <small>
                会话 {item.conversation_id.slice(-6)} · 记录 v
                {item.context_version} / 当前 v{item.current_context_version}
                {item.context_version !== item.current_context_version
                  ? " · 历史轮次"
                  : ""}
              </small>
              <button
                className="secondary"
                aria-pressed={selected?.id === item.id}
                onClick={() => setSelected(item)}
              >
                查看这条会话原文
              </button>
            </article>
          ))}
          {!loading && !error && !items.length && (
            <p>目前没有记录到需复核的处理事项。这不表示 AI 已理解所有聊天。</p>
          )}
          {selected && (
            <section className="review-panel">
              <h3>来源会话 {selected.conversation_id.slice(-6)}</h3>
              {contextError && <p role="alert">{contextError}</p>}
              {messages.map((m) => (
                <article className="message" key={m.id}>
                  <small>
                    {m.direction === "incoming" ? "客户" : "商户"} · r
                    {m.revision}
                    {m.id === selected.message_id ? " · 触发消息" : ""}
                  </small>
                  <p>
                    {m.revoked
                      ? "已撤回，不可用于确认"
                      : (m.text ?? "无可读取文字，请核对附件")}
                  </p>
                </article>
              ))}
              {!messages.length && !contextError && <p>尚无可读取原文。</p>}
              <h3>该会话已有工单</h3>
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
              <button disabled>保存人工归单／延期跟进</button>
              <p className="availability-note">
                归单与延期保存接口尚未交付；查看原文和已有工单不会替你完成归属确认。
              </p>
            </section>
          )}
        </div>
        <aside className="panel">
          <h2>工单缺项与含糊回复</h2>
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
                      {key === "schedule" ? "时间" : "地址"}：
                      {fieldValue(f.value)} ·{" "}
                      {f.status === "missing"
                        ? "等待客户提供"
                        : f.status === "needs_review"
                          ? "原文或含义需要复核"
                          : "等待客户核实和商户确认"}
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
                        ? "客户回复含糊，不能默认同意"
                        : c.customer_confirmation === "confirmed"
                          ? "客户已确认，等待商户核对"
                          : "客户尚未明确确认"}
                    </p>
                  ))}
                <button className="secondary" onClick={() => onOpenOrder(o.id)}>
                  核对工单和来源
                </button>
              </article>
            ))}
          <h2>附件与部分结果</h2>
          <p>
            到 WhatsApp
            消息页查看附件、部分文字、来源版本和人工确认。处理失败或结果未知不会自动重发；扫描
            PDF 的文字识别和真实语音理解仍未交付。
          </p>
          <button className="secondary" onClick={onConnect}>
            前往消息与附件
          </button>
        </aside>
      </div>
    </section>
  );
}
