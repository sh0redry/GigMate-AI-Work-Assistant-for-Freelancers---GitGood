import { t, localized } from "./i18n.ts";
import type { Action, ApprovalSnapshot } from "./approvals-api.ts";
export const actionStates: Record<Action["state"], string> = localized({
  draft: "草稿未提交",
  pending_approval: "待核对批准",
  approved: "已批准，尚未发送",
  executing: "正在执行",
  succeeded: "执行完成",
  failed: "执行失败",
  result_unknown: "执行结果待核对",
  cancelled: "已关闭",
  expired: "已过期",
});
export const deliveryStates: Record<Action["delivery_status"], string> =
  localized({
    not_submitted: "尚未提交发送",
    accepted: "发送服务已接收",
    sent: "已发送",
    delivered: "已送达",
    read: "对方已读",
    unknown: "送达结果未知",
  });
export const closedReasons: Record<string, string> = localized({
  resolved: "缺项已补齐，不再需要此问题",
  order_completed: "工单已完成",
  order_cancelled: "工单已取消",
  superseded: "新消息使旧草稿失效",
  source_changed: "原文已编辑或撤回",
  answered: "已有可用时间，不再需要此问题",
  expired: "超过有效期",
  rejected: "你拒绝了此草稿",
  cancelled: "你取消了此草稿",
  work_order_changed: "工单已变化",
  consent_revoked: "会话授权已撤回",
});
export function approvalBinding(data: ApprovalSnapshot) {
  return JSON.stringify({
    action: data.action,
    orderVersion: data.order?.version,
    orderStatus: data.order?.status,
    context: data.conversation?.context_version,
    contextError: data.contextError,
    sources: data.action?.sources.map(
      (s) =>
        data.messages.find(
          (m) => m.id === s.message_id && m.revision === s.message_revision,
        ) ?? null,
    ),
  });
}
export function sourceReady(data: ApprovalSnapshot) {
  return (
    !!data.action &&
    !!data.conversation &&
    data.action.recipient === data.conversation.id &&
    data.action.sources.every(
      (s) =>
        data.messages.some(
          (m) =>
            m.id === s.message_id &&
            m.revision === s.message_revision &&
            !m.revoked &&
            m.text !== null,
        ) &&
        !data.messages.some(
          (m) => m.id === s.message_id && m.revision > s.message_revision,
        ),
    )
  );
}
export function approveProblem(data: ApprovalSnapshot, now: number) {
  const a = data.action;
  if (!a || a.state !== "pending_approval")
    return t("只有待核对的草稿可以批准。");
  if (Date.parse(a.expires_at) <= now) return t("这份草稿已过期，请刷新查看。");
  if (!sourceReady(data)) return t("收件会话或原文依据无法核对，不能批准。");
  if (!data.order || ["completed", "cancelled"].includes(data.order.status))
    return t("当前工单已结束，不能批准。");
  if (
    data.order.version !== a.bound_work_order_version ||
    data.conversation?.context_version !== a.bound_context_version
  )
    return t("工单或聊天已变化，请刷新后核对新草稿。");
  return "";
}
export function reissueProblem(data: ApprovalSnapshot) {
  const a = data.action;
  if (!a?.reissuable || !["cancelled", "expired"].includes(a.state))
    return t("当前草稿不允许重新提问。");
  if (
    !sourceReady(data) ||
    !data.order ||
    ["completed", "cancelled"].includes(data.order.status)
  )
    return t("当前来源、授权或工单状态不允许重新提问。");
  if (
    a.bound_context_version === data.conversation?.context_version &&
    data.actions.some(
      (old) =>
        old.id !== a.id &&
        old.work_order_id === a.work_order_id &&
        old.bound_context_version === a.bound_context_version &&
        old.trigger === a.trigger &&
        JSON.stringify(old.sources) === JSON.stringify(a.sources),
    )
  )
    return t("这一轮聊天已经重新提问过。等待新消息后再核对，避免重复请求。");
  return "";
}

export function triggerDescription(
  trigger: string,
  openItems: readonly string[] = [],
) {
  if (
    trigger === "schedule_conflict" ||
    trigger.startsWith("schedule_conflict:")
  )
    return t("客户提出的时间与已有安排冲突");
  if (trigger === "open_items" || trigger.startsWith("open_items:")) {
    const labels: Record<string, string> = {
      missing_schedule: t("等待客户提供日期和时间"),
      verify_schedule: t("等待客户核实日期和时间"),
      missing_time: t("只有日期，等待客户说明几点"),
      missing_address: t("等待客户提供地址"),
      verify_address: t("等待客户核实地址"),
    };
    const found = (
      openItems.length
        ? openItems
        : (trigger.split(":").at(-1)?.split(/[+,]/) ?? [])
    )
      .map((code) => labels[code])
      .filter(Boolean);
    return found.length
      ? found.join("；")
      : t("工单还有未确认的信息，请核对完整正文和来源");
  }
  return t("需要人工核对业务含义；请对照完整正文和来源");
}
