import { t } from "./i18n.ts";
import { stableShare, privateReadDenied } from "./read-cache";
import { useStableState as useState } from "./useStableState";
import { useCallback, useEffect, useMemo, useRef } from "react";
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
  triggerDescription,
  approvalBinding,
  approveProblem,
  reissueProblem,
} from "./approval-view";
import { friendlyInstant, messageAnchor } from "./work-order-view";

type Props = {
  csrf: string;
  accountId: string;
  onSessionExpired: () => void;
  onBusyChange: (busy: boolean) => void;
  onOpenOrder?: (id: string) => void;
  api?: ApprovalsApi;
};
export function ApprovalsWorkspace({
  csrf,
  accountId,
  onSessionExpired,
  onBusyChange,
  onOpenOrder,
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
  const [, setUpdatedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [review, setReview] = useState<string | null>(null);
  const [, setConsent] = useState(false);
  const [reason, setReason] = useState("");
  const lastData = useRef<ApprovalSnapshot | null>(null),
    checkedAt = useRef(0),
    hasData = useRef(false);
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
    setLoading(!hasData.current);
    try {
      const next = await api.load(selected, controller.signal);
      if (!mounted.current || generation.current !== id) return;
      checkedAt.current = Date.now();
      hasData.current = true;
      const shared = stableShare(lastData.current, next);
      if (shared !== lastData.current) setUpdatedAt(Date.now());
      lastData.current = shared;
      setData(shared);
      setStale(false);
      setError("");

      if (!selected && next.action) setSelected(next.action.id);
    } catch (failure) {
      if (
        !mounted.current ||
        generation.current !== id ||
        controller.signal.aborted
      )
        return;
      if (privateReadDenied(failure)) {
        setData(null);
        hasData.current = false;
      }
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
            : t("暂时无法读取审批列表，请刷新。"),
        );
    } finally {
      if (mounted.current && generation.current === id) setLoading(false);
    }
  }, [api, selected, onSessionExpired]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const poll = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
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
      setNotice(t("草稿、工单或原文已更新，请重新核对。"));
    }
  }, [binding, review]);
  const action = data?.action;
  const detailReady = !!action && action.id === selected;
  const attempt = api.attempt();
  const fresh =
    detailReady &&
    !stale &&
    !loading &&
    !busy &&
    now - checkedAt.current < 10000;
  // A fresh read of this exact draft is the check; the backend still
  // rejects stale versions, so no extra tick box is needed for approval.
  const reviewed = fresh;
  const approveBlocked = data ? approveProblem(data, now) : t("请先读取草稿。");
  const reissueBlocked = data ? reissueProblem(data) : t("请先读取草稿。");
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
    const note = reason.trim() || t("商户选择不发送这条回复");
    if ((operation === "reject" || operation === "cancel") && note.length > 500)
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
              note,
            );
      if (!mounted.current) return;
      setNotice(
        result.state === "approved"
          ? t("已批准。下一步：回到工单点「发送给客人」。")
          : operation === "reissue"
            ? t("新的待审批草稿已生成，需要再次核对批准。")
            : t("操作结果已确认，正在重新读取当前状态。"),
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
            : t("操作结果暂未确认，请核对原请求。"),
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
    <section aria-label={t("回复审批工作台")}>
      <div className="page-heading">
        <div>
          <h1>{t("回复审批")}</h1>
          <p>
            {t("所有等你批准的回复都在这里。批准后再点「发送」才会发给客人。")}
          </p>
        </div>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={() => void refresh()}
        >
          {t("刷新")}
        </button>
      </div>
      {(error || notice || loading || (stale && data)) && (
        <div className="notice" role="status" aria-live="polite">
          {error || notice || (loading ? t("正在读取…") : "")}
          {stale && data && (
            <p>{t("网络不稳，下面是上次读到的内容，暂时不能操作。")}</p>
          )}
        </div>
      )}
      {api.storageError() && (
        <p className="notice stale">{api.storageError()}</p>
      )}
      {attempt && (
        <div className="notice stale" role="alert">
          <strong>{t("有一笔原请求等待核对")}</strong>
          <p>
            {t(
              "刷新只读取状态，不会再次批准。核对这份草稿后，可用原请求、原版本和原编号核对结果；不会创建另一笔请求。",
            )}
          </p>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setSelected(attempt.actionId)}
          >
            {t("查看待核对原请求")}
          </button>
        </div>
      )}
      <div className="approval-grid">
        <aside className="panel">
          <h2>{t("草稿与历史")}</h2>
          <label>
            {t("审批筛选")}
            <select
              value={filter}
              disabled={busy}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">{t("全部历史")}</option>
              {Object.entries(actionStates).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {!!selected && !visibleSelected && (
            <p>{t("当前选择不在筛选结果中，右侧仍保留该草稿。")}</p>
          )}
          {shown.length === 0 && !selected && (
            <p>
              {data ? t("此筛选下没有草稿。") : t("等待审批列表。")}{" "}
              {t(
                "新的回复草稿会显示在这里，请稍后刷新；没有草稿不代表已经发送。",
              )}
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
                  t("所属工单未载入")}
              </strong>
              <br />
              <small>{actionStates[a.state]}</small>
            </button>
          ))}
        </aside>
        <div className="panel">
          {!detailReady || !data ? (
            <p>{t("选择一份草稿，查看收件会话、正文和原文依据。")}</p>
          ) : (
            <>
              <h2>{data.order?.summary ?? t("当前工单")}</h2>
              <p>
                <strong>{actionStates[action.state]}</strong> ·{" "}
                {deliveryStates[action.delivery_status]}
              </p>
              <dl className="approval-facts">
                <dt>{t("为什么要回复")}</dt>
                <dd>{triggerDescription(action.trigger, action.open_items)}</dd>
                <dt>{t("发给")}</dt>
                <dd>
                  {t(
                    "「{0}」的客人 · WhatsApp",
                    data.order?.summary ?? t("当前工单"),
                  )}
                </dd>
                <dt>{t("回复内容")}</dt>
                <dd className="reply-body">{action.body}</dd>
                <dt>{t("有效到")}</dt>
                <dd>
                  {friendlyInstant(action.expires_at)}
                  {Date.parse(action.expires_at) <= now && t("（已到期）")}
                </dd>
              </dl>
              {action.closed_reason && (
                <p>
                  {t("关闭原因：")}
                  {closedReasons[action.closed_reason] ?? t("这条回复已关闭。")}
                </p>
              )}
              <h3>{t("客人原话")}</h3>
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
                      {t("客人")}
                      {m ? ` · ${friendlyInstant(m.occurred_at)}` : ""}
                    </small>
                    <p>
                      {m
                        ? m.revoked
                          ? t("原文已撤回，不能据此批准。")
                          : (m.text ?? t("原文未提供文字"))
                        : t("这条消息暂时读不到。")}
                    </p>
                  </div>
                );
              })}
              {approveBlocked && action.state === "pending_approval" && (
                <p className="notice stale">{approveBlocked}</p>
              )}
              <div className="approval-buttons">
                {attempt ? (
                  <button
                    disabled={!reviewed || !canRetry || !!api.storageError()}
                    onClick={() => void perform("retry")}
                  >
                    {t("重试上次操作")}
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
                          {t("批准这条回复")}
                        </button>
                        <button
                          className="secondary"
                          disabled={!reviewed || writesBlocked}
                          onClick={() => void perform("reject")}
                        >
                          {t("不发这条")}
                        </button>
                      </>
                    )}
                    {action.state === "approved" && (
                      <>
                        {onOpenOrder && (
                          <button
                            onClick={() => onOpenOrder(action.work_order_id)}
                          >
                            {t("回到工单去发送")}
                          </button>
                        )}
                        <button
                          className="secondary"
                          disabled={!reviewed || writesBlocked}
                          onClick={() => void perform("cancel")}
                        >
                          {t("不发这条")}
                        </button>
                      </>
                    )}
                    {action.reissuable && (
                      <button
                        className="secondary"
                        disabled={
                          !reviewed || writesBlocked || !!reissueBlocked
                        }
                        onClick={() => void perform("reissue")}
                      >
                        {t("重新生成回复")}
                      </button>
                    )}
                  </>
                )}
              </div>
              <details className="quiet">
                <summary>{t("技术信息")}</summary>
                <small>
                  {t("聊天编号")} <code>{action.recipient}</code>
                  <br />
                  {t("草稿第")}
                  {action.revision} {t("版；工单")}{" "}
                  {action.bound_work_order_version} {t("→ 当前")}{" "}
                  {data.order?.version ?? t("未知")}
                  {t("；聊天")} {action.bound_context_version} {t("→ 当前")}{" "}
                  {data.conversation?.context_version ?? t("不可读取")}
                </small>
              </details>
              {["executing", "result_unknown"].includes(action.state) && (
                <p>{t("执行结果由后端核对。此页面不会重新发送消息。")}</p>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
