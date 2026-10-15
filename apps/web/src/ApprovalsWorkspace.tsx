import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  approvalsApi,
  type ApprovalsApi,
  type ApprovalSnapshot,
  type Operation,
} from "./approvals-api";
import {
  actionStates,
  deliveryStates,
  closedReasons,
  approvalBinding,
  approveProblem,
  reissueProblem,
} from "./approval-view";
import { instant, messageAnchor } from "./work-order-view";

type Props = {
  csrf: string;
  accountId: string;
  onSessionExpired: () => void;
  onBusyChange: (busy: boolean) => void;
  api?: ApprovalsApi;
};
export function ApprovalsWorkspace({
  csrf,
  accountId,
  onSessionExpired,
  onBusyChange,
  api: supplied,
}: Props) {
  const api = useMemo(
    () => supplied ?? approvalsApi(csrf, accountId),
    [supplied, csrf, accountId],
  );
  const [data, setData] = useState<ApprovalSnapshot | null>(null);
  const [selected, setSelected] = useState(api.attempt()?.actionId ?? "");
  const [filter, setFilter] = useState("pending_approval");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [stale, setStale] = useState(true);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [review, setReview] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [reason, setReason] = useState("");
  const mounted = useRef(false);
  const writing = useRef(false);
  const generation = useRef(0);
  const readController = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    if (writing.current) return;
    const id = ++generation.current;
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    setLoading(true);
    try {
      const next = await api.load(selected, controller.signal);
      if (!mounted.current || generation.current !== id) return;
      setData(next);
      setStale(false);
      setError("");
      setUpdatedAt(Date.now());
      if (!selected && next.action) setSelected(next.action.id);
    } catch (failure) {
      if (
        !mounted.current ||
        generation.current !== id ||
        controller.signal.aborted
      )
        return;
      setStale(true);
      setReview(null);
      setConsent(false);
      if ((failure as { code?: string }).code === "UNAUTHENTICATED") {
        setData(null);
        onSessionExpired();
      } else
        setError(
          failure instanceof Error
            ? failure.message
            : "暂时无法读取审批列表，请刷新。",
        );
    } finally {
      if (mounted.current && generation.current === id) setLoading(false);
    }
  }, [api, selected, onSessionExpired]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const poll = setInterval(() => void refresh(), 5000);
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      mounted.current = false;
      ++generation.current;
      readController.current?.abort();
      clearInterval(poll);
      clearInterval(clock);
    };
  }, [refresh]);
  useEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);
  useEffect(() => {
    setReview(null);
    setConsent(false);
    setReason("");
  }, [selected]);
  const binding = data ? approvalBinding(data) : "";
  useEffect(() => {
    if (review && review !== binding) {
      setReview(null);
      setConsent(false);
      setNotice("草稿、工单或原文已更新，请重新核对。");
    }
  }, [binding, review]);
  const action = data?.action;
  const detailReady = !!action && action.id === selected;
  const attempt = api.attempt();
  const fresh =
    detailReady && !stale && !loading && !busy && now - updatedAt < 10000;
  const reviewed = fresh && review === binding && consent;
  const approveBlocked = data ? approveProblem(data, now) : "请先读取草稿。";
  const reissueBlocked = data ? reissueProblem(data) : "请先读取草稿。";
  const canRetry =
    !!attempt &&
    detailReady &&
    attempt.actionId === action.id &&
    attempt.hash === action.snapshot_hash;
  const writesBlocked = !!attempt || !!api.storageError();
  const shown = (data?.actions ?? []).filter(
    (a) => filter === "all" || a.state === filter,
  );
  const visibleSelected = shown.some((a) => a.id === selected);
  async function perform(operation: Operation | "retry") {
    if (writing.current || !reviewed || !data?.action) return;
    if (operation === "retry" ? !canRetry : writesBlocked) return;
    if (
      (operation === "approve" && approveBlocked) ||
      (operation === "reissue" && reissueBlocked)
    )
      return;
    if (
      (operation === "reject" || operation === "cancel") &&
      (!reason.trim() || reason.trim().length > 500)
    )
      return;
    writing.current = true;
    ++generation.current;
    readController.current?.abort();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result =
        operation === "retry"
          ? await api.retryOriginal()
          : await api.submit(
              data.action,
              operation,
              data.conversation?.context_version ??
                data.action.bound_context_version,
              reason,
            );
      if (!mounted.current) return;
      setNotice(
        result.state === "approved"
          ? "批准已保存；消息尚未提交发送。"
          : operation === "reissue"
            ? "新的待审批草稿已生成，需要再次核对批准。"
            : "操作结果已确认，正在重新读取当前状态。",
      );
      if (operation === "reissue") setSelected(result.id);
    } catch (failure) {
      if (!mounted.current) return;
      if ((failure as { code?: string }).code === "UNAUTHENTICATED") {
        setData(null);
        onSessionExpired();
      } else
        setError(
          failure instanceof Error
            ? failure.message
            : "操作结果暂未确认，请核对原请求。",
        );
    } finally {
      writing.current = false;
      if (mounted.current) {
        setBusy(false);
        setReview(null);
        setConsent(false);
        setStale(true);
        void refresh();
      }
    }
  }
  return (
    <section aria-label="回复审批工作台">
      <div className="intro">
        <p className="eyebrow">回复审批</p>
        <h1>先核对收件会话和正文，再批准。</h1>
        <p>
          这里保存你的批准决定。当前尚未接通 WhatsApp 发送；批准不等于已发送。
        </p>
      </div>
      <div className="notice" role="status" aria-live="polite">
        {error ||
          notice ||
          (loading ? "正在读取审批数据…" : "没有你的明确批准，草稿不会执行。")}
        {stale && data && <p>下面是上次读取的数据，当前不能提交操作。</p>}
      </div>
      {api.storageError() && (
        <p className="notice stale">{api.storageError()}</p>
      )}
      {attempt && (
        <div className="notice stale" role="alert">
          <strong>有一笔原请求等待核对</strong>
          <p>
            刷新只读取状态，不会再次批准。核对这份草稿后，可用原请求、原版本和原编号核对结果；不会创建另一笔请求。
          </p>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setSelected(attempt.actionId)}
          >
            查看待核对原请求
          </button>
        </div>
      )}
      <div className="replay-tools">
        <small>
          {updatedAt
            ? `最近读取：${instant(new Date(updatedAt).toISOString())}`
            : "尚未读取"}
        </small>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={() => void refresh()}
        >
          刷新审批
        </button>
      </div>
      <div className="approval-grid">
        <aside className="panel">
          <h2>草稿与历史</h2>
          <label>
            审批筛选
            <select
              value={filter}
              disabled={busy}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">全部历史</option>
              {Object.entries(actionStates).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {!!selected && !visibleSelected && (
            <p>当前选择不在筛选结果中，右侧仍保留该草稿。</p>
          )}
          {shown.length === 0 && (
            <p>
              {data ? "此筛选下没有草稿。" : "等待审批列表。"}{" "}
              没有草稿不代表已经发送，也不会自动生成演示内容。
            </p>
          )}
          {shown.map((a) => (
            <button
              key={a.id}
              className={`order ${selected === a.id ? "active" : ""}`}
              disabled={busy}
              aria-pressed={selected === a.id}
              onClick={() => setSelected(a.id)}
            >
              <strong>
                {data?.orders.find((o) => o.id === a.work_order_id)?.summary ??
                  "所属工单未载入"}
              </strong>
              <br />
              {actionStates[a.state]}
              <br />
              <small>有效至 {instant(a.expires_at)}</small>
            </button>
          ))}
        </aside>
        <div className="panel">
          {!detailReady || !data ? (
            <p>选择一份草稿，查看收件会话、正文和原文依据。</p>
          ) : (
            <>
              <h2>{data.order?.summary ?? "当前工单"}</h2>
              <p>
                <strong>{actionStates[action.state]}</strong> ·{" "}
                {deliveryStates[action.delivery_status]}
              </p>
              <dl className="approval-facts">
                <dt>为什么需要回复</dt>
                <dd>
                  {action.trigger === "schedule_conflict"
                    ? "客户提出的时间与已有安排冲突"
                    : "后端未提供可识别原因"}
                </dd>
                <dt>收件会话（系统编号）</dt>
                <dd>
                  <code>{action.recipient}</code>
                  <br />
                  <small>
                    这是当前工单关联的会话；实际 WhatsApp
                    收件人映射和发送桥接尚未接通。
                  </small>
                </dd>
                <dt>草稿正文</dt>
                <dd className="reply-body">{action.body}</dd>
                <dt>有效期</dt>
                <dd>
                  {instant(action.expires_at)}
                  {Date.parse(action.expires_at) <= now && "（已到期）"}
                </dd>
                <dt>版本核对</dt>
                <dd>
                  草稿第 {action.revision} 版；工单{" "}
                  {action.bound_work_order_version} → 当前{" "}
                  {data.order?.version ?? "未知"}；聊天{" "}
                  {action.bound_context_version} → 当前{" "}
                  {data.conversation?.context_version ?? "不可读取"}
                </dd>
              </dl>
              {action.closed_reason && (
                <p>
                  关闭原因：
                  {closedReasons[action.closed_reason] ??
                    "后端已关闭此草稿，请核对当前业务。"}
                </p>
              )}
              {action.closed_note && <p>你记录的原因：{action.closed_note}</p>}
              {action.approved_at && (
                <p>批准时间：{instant(action.approved_at)}</p>
              )}
              <h3>原文依据</h3>
              {data.contextError && <p>{data.contextError}</p>}
              {action.sources.map((s) => {
                const m = data.messages.find(
                  (m) =>
                    m.id === s.message_id && m.revision === s.message_revision,
                );
                return (
                  <div
                    className="source-message"
                    key={`${s.message_id}:${s.message_revision}`}
                    id={messageAnchor(s.message_id, s.message_revision)}
                  >
                    <small>
                      消息 {s.message_id} · 第 {s.message_revision} 版 ·{" "}
                      {m ? instant(m.occurred_at) : "该版本不可读取"}
                    </small>
                    <p>
                      {m
                        ? m.revoked
                          ? "原文已撤回，不能据此批准。"
                          : (m.text ?? "原文未提供文字")
                        : "没有可核对的原文，不补造内容。"}
                    </p>
                  </div>
                );
              })}
              {approveBlocked && action.state === "pending_approval" && (
                <p className="notice stale">{approveBlocked}</p>
              )}
              {action.reissuable && reissueBlocked && <p>{reissueBlocked}</p>}
              <button
                className="secondary"
                disabled={!fresh}
                onClick={() => {
                  setReview(binding);
                  setConsent(false);
                }}
              >
                核对这份草稿
              </button>
              {review === binding && (
                <div className="approval-review">
                  <h3>本次核对</h3>
                  <p>
                    接收会话：<code>{action.recipient}</code>
                  </p>
                  <p className="reply-body">{action.body}</p>
                  <label className="confirm-check">
                    <input
                      type="checkbox"
                      checked={consent}
                      disabled={!fresh}
                      onChange={(e) => setConsent(e.target.checked)}
                    />
                    我已核对收件会话、完整正文、原文与版本。
                  </label>
                  {!attempt && (
                    <label>
                      拒绝／取消原因
                      <textarea
                        maxLength={500}
                        value={reason}
                        disabled={busy}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="例如：需要先和客户确认其他时间"
                      />
                    </label>
                  )}
                  <div className="approval-buttons">
                    {attempt ? (
                      <button
                        disabled={
                          !reviewed || !canRetry || !!api.storageError()
                        }
                        onClick={() => void perform("retry")}
                      >
                        核对后重试原请求
                      </button>
                    ) : (
                      <>
                        {action.state === "pending_approval" && (
                          <>
                            <button
                              disabled={
                                !reviewed || writesBlocked || !!approveBlocked
                              }
                              onClick={() => void perform("approve")}
                            >
                              批准这份草稿
                            </button>
                            <button
                              className="secondary"
                              disabled={
                                !reviewed || writesBlocked || !reason.trim()
                              }
                              onClick={() => void perform("reject")}
                            >
                              拒绝草稿
                            </button>
                          </>
                        )}
                        {["pending_approval", "approved"].includes(
                          action.state,
                        ) && (
                          <button
                            className="secondary"
                            disabled={
                              !reviewed || writesBlocked || !reason.trim()
                            }
                            onClick={() => void perform("cancel")}
                          >
                            取消待执行草稿
                          </button>
                        )}
                        {action.reissuable && (
                          <button
                            disabled={
                              !reviewed || writesBlocked || !!reissueBlocked
                            }
                            onClick={() => void perform("reissue")}
                          >
                            重新生成待审批问题
                          </button>
                        )}
                      </>
                    )}
                  </div>
                  <small>
                    拒绝和取消只关闭本机尚未执行的草稿；执行中的发送不能假装撤回。重新提问会生成新草稿，不会直接发送。
                  </small>
                </div>
              )}
              {["executing", "result_unknown"].includes(action.state) && (
                <p>执行结果由后端核对。此页面不会重新发送消息。</p>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
