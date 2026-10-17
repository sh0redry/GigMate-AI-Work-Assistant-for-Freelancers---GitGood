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
