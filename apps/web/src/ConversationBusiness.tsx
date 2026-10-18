import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "./i18n.ts";
import { conversationApi, type AgentDraft } from "./conversation-api";
import type { TimelineMessage } from "./waha-sync-api";
import type { Order } from "./workspace-api";
import { fieldNames, fieldValue, orderStates } from "./work-order-view";
import { sourceMatch } from "./conversation-view";

export function ConversationBusiness({
  csrf,
  conversation,
  messages,
  enabled,
  busy,
  onBusyChange,
  onOpenOrder,
  onLocate,
  onAdopt,
  onSessionExpired,
}: {
  csrf: string;
  conversation: string;
  messages: TimelineMessage[];
  enabled: boolean;
  busy: boolean;
  onBusyChange: (value: boolean) => void;
  onOpenOrder: (id: string) => void;
  onLocate: (id: string, revision: number) => void;
  onAdopt: (text: string) => void;
  onSessionExpired: () => void;
}) {
  const api = useMemo(() => conversationApi(csrf), [csrf]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [selected, setSelected] = useState("");
  const [drafts, setDrafts] = useState<AgentDraft[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [partial, setPartial] = useState(false);
  const [available, setAvailable] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [reviewDraft, setReviewDraft] = useState<AgentDraft | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const attempt = useRef(false);
  const lifetime = useRef<{
    active: boolean;
    abort: AbortController;
    release: (() => void) | null;
  } | null>(null);
  useEffect(() => {
    const current = {
      active: true,
      abort: new AbortController(),
      release: null as (() => void) | null,
    };
    lifetime.current = current;
    return () => {
      current.active = false;
      current.abort.abort();
      current.release?.();
      current.release = null;
    };
  }, [api, conversation]);
  const order = orders.find((value) => value.id === selected);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setAvailable(false);
    setReviewDraft(null);
    setDrafts([]);
    void (async () => {
      try {
        const result = await api.orders(abort.signal);
        if (abort.signal.aborted) return;
        const linked = result.items.filter((value) =>
          value.conversation_ids.includes(conversation),
        );
        setOrders(linked);
        setPartial(result.partial);
        if (selected && !linked.some((value) => value.id === selected))
          setSelected("");
        setNotice("");
        if (!selected) return;
        const current = linked.find((value) => value.id === selected);
        if (!current) return;
        const resultDrafts = await api.drafts(
          current,
          conversation,
          abort.signal,
        );
        if (!abort.signal.aborted) {
          setDrafts(resultDrafts.items);
          setAvailable(true);
          setPartial(result.partial || resultDrafts.partial);
        }
      } catch (error) {
        if (!abort.signal.aborted) {
          if (
            (error as { code?: string }).code !== "CONVERSATION_API_UNAVAILABLE"
          )
            setOrders([]);
          setDrafts([]);
          setNotice(error instanceof Error ? error.message : t("查询失败"));
          if ((error as { code?: string }).code === "UNAUTHENTICATED")
            onSessionExpired();
        }
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    })();
    return () => abort.abort();
  }, [api, conversation, selected, refresh, onSessionExpired]);
  // Any accepted message revision/status or an order selection invalidates the local review.
  const binding = JSON.stringify(
    messages.map((m) => [m.id, m.revision, m.revoked, m.observed_at]),
  );
  useEffect(() => {
    setReviewDraft(null);
    setAvailable(false);
  }, [binding]);
  const eligible = drafts.filter(
    (d) =>
      d.status === "proposed" &&
      d.proposal_id &&
      d.execution_authority === false &&
      d.base_work_order_version === order?.version &&
      Date.parse(d.expires_at) > Date.now(),
  );
  async function adopt() {
    const current = lifetime.current;
    if (
      !current?.active ||
      !reviewDraft ||
      !order ||
      !enabled ||
      busy ||
      attempt.current ||
      uncertain ||
      !available
    )
      return;
    if (!window.confirm(t("采用建议会替换当前文字输入，但不会发送。继续吗？")))
      return;
    attempt.current = true;
    onBusyChange(true);
    current.release = () => onBusyChange(false);
    try {
      const value = await api.consume(reviewDraft, current.abort.signal);
      if (!current.active || current.abort.signal.aborted) return;
      onAdopt(value.text);
      setReviewDraft(null);
      setRefresh((value) => value + 1);
    } catch (error) {
      if (!current.active || current.abort.signal.aborted) return;
      setNotice(error instanceof Error ? error.message : t("查询失败"));
      if ((error as { code?: string }).code === "DRAFT_RESULT_UNKNOWN")
        setUncertain(true);
      if ((error as { code?: string }).code === "UNAUTHENTICATED")
        onSessionExpired();
    } finally {
      if (current.active) {
        attempt.current = false;
        current.release?.();
        current.release = null;
      }
    }
  }
  return (
    <aside
      className="conversation-business"
      aria-label={t("关联工单与 AI 建议")}
    >
      <h2>{t("关联工单与 AI 建议")}</h2>
      <p>{t("一个聊天可以有多张工单，请明确选择本次业务。")}</p>
      {notice && <p role="status">{notice}</p>}
      {partial && (
        <p className="notice">
          {t("仅展示本次有界查询结果，列表可能不完整。")}
        </p>
      )}
      <button
        className="secondary"
        disabled={busy || loading}
        onClick={() => setRefresh((value) => value + 1)}
      >
        {t("刷新工单与建议")}
      </button>
      <label>
        {t("选择关联工单")}
        <select
          value={selected}
          disabled={busy || loading}
          onChange={(e) => {
            setSelected(e.target.value);
            setReviewDraft(null);
          }}
        >
          <option value="">{t("请选择本次工单")}</option>
          {orders.map((value) => (
            <option key={value.id} value={value.id}>
              {value.summary}
            </option>
          ))}
        </select>
      </label>
      {!loading && !orders.length && (
        <p>{t("本次未找到关联工单。可先选择客户消息，再核对新建工单。")}</p>
      )}
      {order && (
        <section>
          <h3>{order.summary}</h3>
          <p>{orderStates[order.status]}</p>
          {Object.entries(order.fields).map(([key, field]) => (
            <div className="conversation-field" key={key}>
              <strong>
                {fieldNames[key as keyof typeof fieldNames] ?? key}
              </strong>
              <p>{fieldValue(field.value)}</p>
              {field.sources.map((source) => (
                <button
                  className="secondary"
                  key={`${source.message_id}:${source.message_revision}`}
                  disabled={busy}
                  onClick={() =>
                    onLocate(source.message_id, source.message_revision)
                  }
                >
                  {sourceMatchInWindow(
                    messages,
                    source.message_id,
                    source.message_revision,
                  )
                    ? t("定位客户原话")
                    : t("查找原文并核对版本")}
                </button>
              ))}
            </div>
          ))}
          <button disabled={busy} onClick={() => onOpenOrder(order.id)}>
            {t("打开工单处理")}
          </button>
          <h3>{t("已有 AI 建议回复")}</h3>
          <p>
            {t(
              "这里只采用后端已有的有效模型建议；重新生成与自动润色尚未接通。",
            )}
          </p>
          {!available && (
            <p>{t("先刷新核对建议；旧版后端可能尚未提供草稿接口。")}</p>
          )}
          {available && !eligible.length && (
            <p>{t("暂无可采用的有效 AI 建议，仍可手动回复。")}</p>
          )}
          {eligible.map((draft) => (
            <button
              className="secondary"
              disabled={busy || !enabled || !available || uncertain}
              key={draft.id}
              onClick={() => setReviewDraft(draft)}
            >
              {t("核对建议回复")} ·{" "}
              {new Date(draft.created_at).toLocaleString()}
            </button>
          ))}
          {reviewDraft && (
            <section
              className="conversation-draft-review"
              aria-label={t("核对建议回复")}
            >
              <p className="conversation-text">{reviewDraft.text}</p>
              <p>
                {t(
                  "建议绑定当前工单和聊天，采用后仍需核对收件人与正文并批准发送。",
                )}
              </p>
              <button
                disabled={busy || !enabled || !available || uncertain}
                onClick={() => void adopt()}
              >
                {t("采用到输入框（不发送）")}
              </button>
            </section>
          )}
          {uncertain && (
            <p role="status">
              {t("采用结果待核对，不会自动重复消费或发送。请查看原草稿记录。")}
            </p>
          )}
        </section>
      )}
    </aside>
  );
}

function sourceMatchInWindow(
  messages: TimelineMessage[],
  id: string,
  revision: number,
) {
  return messages.some((message) => sourceMatch(message, id, revision));
}
