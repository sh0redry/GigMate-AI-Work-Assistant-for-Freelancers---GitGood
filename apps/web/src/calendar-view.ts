import type { Calendar, Order } from "./workspace-api.ts";
import { onDay } from "./work-order-view.ts";
export function todayInHongKong(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  return ["year", "month", "day"]
    .map((k) => parts.find((p) => p.type === k)!.value)
    .join("-");
}
export function shiftDay(day: string, amount: number) {
  const date = new Date(day + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}
export function monthDays(month: string) {
  const start = month + "-01";
  const weekday = (new Date(start + "T12:00:00Z").getUTCDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) => shiftDay(start, i - weekday));
}
export function shiftMonth(month: string, amount: number) {
  const date = new Date(month + "-01T12:00:00Z");
  date.setUTCMonth(date.getUTCMonth() + amount);
  return date.toISOString().slice(0, 7);
}
export function exportProblem(event: Calendar, order?: Order) {
  if (!order) return "无法核对关联工单。";
  if (["completed", "cancelled"].includes(order.status))
    return "已结束工单仅保留历史，不能导出。";
  if (
    event.work_order_version > order.version ||
    !sameSchedule(event.schedule, order.fields.schedule.value) ||
    JSON.stringify(event.sources) !==
      JSON.stringify(order.fields.schedule.sources)
  )
    return "预约与工单版本不一致，请刷新核对。";
  if (
    event.tentative ||
    event.schedule.kind !== "timed" ||
    order.fields.schedule.status !== "confirmed" ||
    !["confirmed", "in_progress", "waiting_customer"].includes(order.status)
  )
    return "暂定或未确认预约不能导出。";
  return "";
}
export function eventsForDay(events: Calendar[], day: string) {
  return events
    .filter((e) => onDay(e, day))
    .sort((a, b) => {
      const start = (e: Calendar) =>
        e.schedule.kind === "date_only" ? e.schedule.date : e.schedule.start_at;
      return start(a).localeCompare(start(b)) || a.id.localeCompare(b.id);
    });
}

function sameSchedule(a: Calendar["schedule"], b: unknown) {
  if (!b || typeof b !== "object") return false;
  const item = b as Calendar["schedule"];
  return (
    a.kind === item.kind &&
    a.timezone === item.timezone &&
    (a.kind === "timed" && item.kind === "timed"
      ? a.start_at === item.start_at && a.end_at === item.end_at
      : a.kind === "date_only" &&
        item.kind === "date_only" &&
        a.date === item.date)
  );
}
export function sortedEvents(events: Calendar[]) {
  const start = (e: Calendar) =>
    e.schedule.kind === "date_only" ? e.schedule.date : e.schedule.start_at;
  return [...events].sort(
    (a, b) => start(a).localeCompare(start(b)) || a.id.localeCompare(b.id),
  );
}
