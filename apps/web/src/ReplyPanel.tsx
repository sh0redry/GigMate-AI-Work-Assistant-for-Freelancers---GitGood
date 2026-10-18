import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  approvalsApi,
  type Action,
  type ApprovalSnapshot,
} from "./approvals-api";
import { approveProblem, deliveryStates } from "./approval-view";
import { allPages, workspaceApi } from "./workspace-api";
import type { Features } from "./features";

type Props = {
  csrf: string;
  accountId: string;
  orderId: string;
  orderSummary: string;
  features: Features;
  /** Changes whenever the surrounding work order data is re-read. */
  refreshKey: unknown;
  onOpenSend?: (actionId: string) => void;
  onConnect?: () => void;
  onOpenApprovals?: () => void;
  onSessionExpired: () => void;
  onBusyChange?: (busy: boolean) => void;
};

const open = new Set(["pending_approval", "approved", "executing"]);

function reasonFor(action: Action) {
  if (action.trigger.startsWith("schedule_conflict"))
    return t("这个时间你已有安排，建议先问客人换个时间：");
  if (action.trigger.startsWith("open_items"))
    return t("还有信息没齐，建议这样问客人：");
  return t("建议这样回复客人：");
}

/**
 * The one place a merchant handles a reply for the work order in front of
 * them: read the suggested text, approve it, then send. Approval and sending
 * remain separate backend facts; this panel only removes the page switching.
 */
export function ReplyPanel({
  csrf,
  accountId,
  orderId,
  orderSummary,
  features,
  refreshKey,
  onOpenSend,
  onConnect,
  onOpenApprovals,
  onSessionExpired,
  onBusyChange,
}: Props) {
  const api = useMemo(() => approvalsApi(csrf, accountId), [csrf, accountId]);
  const request = useMemo(() => workspaceApi(csrf), [csrf]);
  const [data, setData] = useState<ApprovalSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loadedAt, setLoadedAt] = useState(0);
  const alive = useRef(true);
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const controller = new AbortController();
      const actions = await allPages<Action>(
        request,
        "/actions",
        signal ?? controller.signal,
      );
      const mine = actions
        .filter((a) => a.work_order_id === orderId && open.has(a.state))
        .sort((a, b) => b.expires_at.localeCompare(a.expires_at));
      const target =
        mine.find((a) => a.state === "pending_approval") ??
        mine.find((a) => a.delivery_status === "not_submitted") ??
        mine[0];
      if (!target) return null;
      return api.load(target.id, signal ?? controller.signal);
    },
    [api, request, orderId],
  );
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    load(controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return;
        setData(next);
        setError("");
        setLoadedAt(Date.now());
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        if (e?.code === "UNAUTHENTICATED") onSessionExpired();
        else setError(t("暂时读不到回复草稿，稍后会自动重试。"));
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, [load, refreshKey, onSessionExpired]);
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);
  const action = data?.action;
  if (!action)
    return notice ? (
      <p role="status">
        {notice}{" "}
        {features.manual_field_editing &&
          t("如果客户已经提供信息，可在下方手动补充／修改字段。")}
      </p>
    ) : null;
  const attempt = api.attempt();
  const problem =
    action.state === "pending_approval" ? approveProblem(data, Date.now()) : "";
  async function act(operation: "approve" | "reject") {
    if (!data?.action || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.submit(
        data.action,
        operation,
        data.conversation?.context_version ?? data.action.bound_context_version,
        operation === "reject" ? t("商户选择不发送这条回复") : "",
      );
      if (!alive.current) return;
      setNotice(
        operation === "approve"
          ? t("已批准。下一步：发送给客人。")
          : t("这条回复不会发出。"),
      );
      const next = await load();
      if (alive.current) {
        setData(next);
        setLoadedAt(Date.now());
      }
    } catch (e) {
      if (!alive.current) return;
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        onSessionExpired();
      else
        setError(
          e instanceof Error ? e.message : t("操作没有完成，请稍后再试。"),
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const approved = action.state !== "pending_approval";
  const submitted = action.delivery_status !== "not_submitted";
  const received = ["delivered", "read"].includes(action.delivery_status);
  return (
    <div className="reply-panel" aria-label={t("回复客人")} role="region">
      <p className="reply-reason">{reasonFor(action)}</p>
      <p className="reply-to">
        {t("发给：「{0}」的客人 · WhatsApp", orderSummary)}
      </p>
      <p className="reply-body">{action.body}</p>
      <ol className="reply-steps" aria-label={t("发送进度")}>
        <li data-done={approved}>{t("你批准")}</li>
        <li data-done={submitted}>{t("发送")}</li>
        <li data-done={received}>{t("客人收到")}</li>
      </ol>
      {error && (
        <p className="notice stale" role="alert">
          {error}
        </p>
      )}
      {notice && !error && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {attempt ? (
        <p className="subtle">
          {t("上一次操作还没确认结果，请到「回复审批」处理。")}{" "}
          {onOpenApprovals && (
            <button className="text-button" onClick={onOpenApprovals}>
              {t("去处理")}
            </button>
          )}
        </p>
      ) : action.state === "pending_approval" ? (
        <>
          <div className="reply-actions">
            <button
              disabled={busy || !!problem || !loadedAt}
              onClick={() => void act("approve")}
            >
              {busy ? t("正在保存…") : t("批准这条回复")}
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void act("reject")}
            >
              {t("不发这条")}
            </button>
          </div>
          {problem ? (
            <p className="subtle">{problem}</p>
          ) : (
            <p className="subtle">
              {t("批准后再点「发送」才会发给客人；想改字可到「回复审批」。")}
            </p>
          )}
        </>
      ) : !submitted ? (
        <div className="reply-actions">
          {features.business_sending && onOpenSend ? (
            <button onClick={() => onOpenSend(action.id)}>
              {t("发送给客人")}
            </button>
          ) : (
            <>
              <button disabled>{t("发送给客人")}</button>
              <p className="subtle">
                {t("还没连接 WhatsApp，连上后才能真正发出。")}{" "}
                {onConnect && (
                  <button className="text-button" onClick={onConnect}>
                    {t("去连接 WhatsApp")}
                  </button>
                )}
              </p>
            </>
          )}
        </div>
      ) : (
        <p className="subtle">
          {deliveryStates[action.delivery_status] ?? t("正在确认发送结果")}
        </p>
      )}
    </div>
  );
}
