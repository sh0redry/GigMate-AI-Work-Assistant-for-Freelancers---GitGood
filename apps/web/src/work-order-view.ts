import { t, localized, getLocale } from "./i18n.ts";
import type {
  Calendar,
  Change,
  Order,
  BusinessSnapshot,
} from "./workspace-api.ts";
import { changeContext } from "./workspace-api.ts";
export const orderStates: Record<Order["status"], string> = localized({
  unclassified: "待归类",
  pending_confirmation: "待确认",
  confirmed: "已确认",
  in_progress: "进行中",
  waiting_customer: "等待顾客",
  completed: "已完成",
  cancelled: "已取消",
});
export const orderActionLabels = localized({
  in_progress: "开始处理",
  waiting_customer: "标记等待客户",
  completed: "完成工单",
  cancelled: "取消工单",
});
export const fieldStates = localized({
  missing: "未提供",
  proposed: "提议",
  confirmed: "已确认",
  needs_review: "待复核",
});
export const customerStates = localized({
  not_requested: "尚未询问",
  pending: "等待顾客确认",
  confirmed: "顾客已确认",
  ambiguous: "回复含糊，待核对",
});
export const taskStates = localized({
  pending: "待处理",
  blocked: "受阻",
  completed: "已完成",
  cancelled: "已取消",
});
export const reviewReasons: Record<string, string> = localized({
  LIVE_EXTRACTION_PENDING: "真实消息理解尚未启用",
  MODEL_OUTCOME_UNKNOWN: "模型调用结果未知，保留原编号，不能自动重试",
  EXTRACTION_NEEDS_REVIEW: "模型未能确定业务含义，需要人工核对",
  ASSIGNMENT_NEEDS_REVIEW: "无法确定属于哪张工单",
  PROCESSING_FAILED: "处理失败，需要核对原文",
  RETRY_EXHAUSTED: "多次处理未完成，需要人工核对",
});
export const fieldNames: Record<Change["field"], string> = localized({
  schedule: "时间安排",
  address: "地址",
  summary: "业务摘要",
  quantity: "数量",
  specification: "规格",
  deadline: "截止时间",
});
export function instant(value: string) {
  return new Date(value).toLocaleString(
    getLocale() === "en" ? "en-HK" : getLocale() === "yue" ? "zh-HK" : "zh-CN",
    {
      timeZone: "Asia/Hong_Kong",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    },
  );
}
// datetime-local can include seconds and milliseconds. Validate the complete
// local value before appending a zone; Date alone silently normalizes Feb 31.
export function hongKongDateTime(value: string): string | null {
  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/,
  );
  if (!match || Number(match[1]) < 1) return null;
  const local = `${value.slice(0, 16)}:${match[6] ?? "00"}.${(match[7] ?? "").padEnd(3, "0")}`;
  const timestamp = Date.parse(`${local}+08:00`);
  if (!Number.isFinite(timestamp)) return null;
  const roundTrip = new Date(timestamp + 8 * 3600000)
    .toISOString()
    .slice(0, -1);
  return roundTrip === local ? new Date(timestamp).toISOString() : null;
}
export function fieldValue(value: unknown): string {
  if (value === null || value === undefined) return t("未提供");
  if (typeof value !== "object") return String(value);
  const item = value as {
    kind?: string;
    date?: string;
    start_at?: string;
    end_at?: string;
    at?: string;
    timezone?: string;
  };
  if (item.kind === "date_only")
    return t("{0} 全天（{1}）", item.date, item.timezone);
  if (item.kind === "instant" && item.at)
    return t("{0}（香港时间）", instant(item.at));
  if (item.kind === "timed" && item.start_at && item.end_at)
    return t(
      "{0} → {1}（香港时间；原时区 {2}）",
      instant(item.start_at),
      instant(item.end_at),
      item.timezone,
    );
  return t("待核对");
}
export function filterOrders(orders: Order[], search: string, status: string) {
  const query = search.trim().toLocaleLowerCase();
  return orders.filter(
    (order) =>
      (status === "all" || order.status === status) &&
      order.summary.toLocaleLowerCase().includes(query),
  );
}
export function onDay(event: Calendar, day: string) {
  if (event.schedule.kind === "date_only") return event.schedule.date === day;
  const start = Date.parse(`${day}T00:00:00+08:00`);
  return (
    Date.parse(event.schedule.start_at) < start + 86400000 &&
    Date.parse(event.schedule.end_at) > start
  );
}
export function reviewBinding(data: BusinessSnapshot, change: Change) {
  const order = data.orders.find((order) => order.id === data.selected);
  return JSON.stringify({
    selected: data.selected,
    version: order?.version,
    context: changeContext(data, change),
    change,
  });
}
export function messageAnchor(id: string, revision: number) {
  return `message-${id}-r${revision}`;
}

export function conflictLabel(data: BusinessSnapshot, calendarId: string) {
  const event = data.calendar.find((event) => event.id === calendarId);
  const order = data.orders.find((order) => order.id === event?.work_order_id);
  return order
    ? order.summary
    : t("未提供标题（日历 {0}）", calendarId.slice(-6));
}
