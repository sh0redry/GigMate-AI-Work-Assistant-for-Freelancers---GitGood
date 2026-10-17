import { t } from "./i18n.ts";
// UI guidance only; server-side ownership/consent/state still govern operations.
export function connectionState({
  enabled,
  uncertain,
  connected,
  state,
}: {
  enabled: boolean;
  uncertain: boolean;
  connected: boolean;
  state?: string;
}) {
  if (!enabled)
    return {
      title: t("接收授权已暂停"),
      help: t("点击「恢复消息接收」重新启用已选会话的接收授权。"),
      action: "refresh",
      tone: "warning",
    } as const;
  if (uncertain)
    return {
      title: t("⚠ 消息可能没有同步：暂时无法确认连接状态"),
      help: t("上次状态已过期或查询失败。请先刷新状态，确认后再操作。"),
      action: "refresh",
      tone: "warning",
    } as const;
  if (connected)
    return {
      title: t("✓ WhatsApp 已连接"),
      help: t("无需再次扫码。消息处理是否就绪，请查看下方处理链路。"),
      action: "refresh",
      tone: "success",
    } as const;
  if (["FAILED", "STOPPED", "failed", "disconnected"].includes(state ?? ""))
    return {
      title: t("⚠ 消息暂时无法同步：WhatsApp 已断开"),
      help: t("重新连接本机 WhatsApp 会话，获取新二维码后用手机扫码。"),
      action: "restart",
      tone: "warning",
    } as const;
  if (state === "SCAN_QR_CODE")
    return {
      title: t("扫描二维码，连接 WhatsApp"),
      help: t("请在手机 WhatsApp 的「关联设备」中扫码；二维码会自动更新。"),
      action: "qr",
      tone: "neutral",
    } as const;
  return {
    title: t("正在确认 WhatsApp 连接"),
    help: t("服务正在准备连接。请刷新状态，暂时无需重复重连。"),
    action: "refresh",
    tone: "neutral",
  } as const;
}

export function pendingIssues<
  T extends { acknowledged_at: string | null; resolution: string | null },
>(issues: T[]) {
  return issues.filter(
    (issue) => !issue.acknowledged_at || issue.resolution === "needs_followup",
  );
}

export function choiceExpired(
  choice: { expires_at: string | null },
  now = Date.now(),
) {
  return (
    choice.expires_at !== null && new Date(choice.expires_at).getTime() <= now
  );
}
