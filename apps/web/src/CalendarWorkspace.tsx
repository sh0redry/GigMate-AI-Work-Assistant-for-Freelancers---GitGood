import { useStableState as useState } from "./useStableState";
import { useEffect, useRef } from "react";
import {
  allPages,
  type Calendar,
  type Order,
  type Task,
  type RequestApi,
} from "./workspace-api";
import { useWorkspaceData } from "./useWorkspaceData";
import {
  eventsForDay,
  sortedEvents,
  exportProblem,
  monthDays,
  shiftDay,
  shiftMonth,
  todayInHongKong,
} from "./calendar-view";
import { calendarFile, saveCalendar } from "./calendar-api";
import { fieldValue, taskStates, orderStates } from "./work-order-view";
import type { Features } from "./features";
async function load(api: RequestApi, signal: AbortSignal) {
  const [orders, calendar, tasks] = await Promise.all([
    allPages<Order>(api, "/work-orders", signal),
    allPages<Calendar>(api, "/calendar-events", signal),
    allPages<Task>(api, "/tasks", signal),
  ]);
  return { orders, calendar, tasks };
}
export function CalendarWorkspace({
  csrf,
  features,
  onSessionExpired,
  onOpenOrder,
}: {
  csrf: string;
  features: Features;
  onSessionExpired: () => void;
  onOpenOrder: (id: string) => void;
}) {
  const downloadController = useRef<AbortController | null>(null);
  useEffect(() => () => downloadController.current?.abort(), []);
  const state = useWorkspaceData(csrf, onSessionExpired, load);
  const [day, setDay] = useState(todayInHongKong),
    [month, setMonth] = useState(day.slice(0, 7)),
    [view, setView] = useState("month"),
    [history, setHistory] = useState(false),
    [taskFilter, setTaskFilter] = useState("active"),
    [notice, setNotice] = useState(""),
    [downloading, setDownloading] = useState("");
  const orders = state.data?.orders ?? [],
    tasks = state.data?.tasks ?? [];
  const byId = new Map(orders.map((o) => [o.id, o]));
  const events = (state.data?.calendar ?? []).filter(
    (e) =>
      history ||
      !["completed", "cancelled"].includes(
        byId.get(e.work_order_id)?.status ?? "",
      ),
  );
  function select(next: string, focus = false) {
    setDay(next);
    setMonth(next.slice(0, 7));
    if (focus)
      queueMicrotask(() =>
        document.getElementById("calendar-day-" + next)?.focus(),
      );
  }
  async function download(event: Calendar) {
    if (
      downloading ||
      state.loading ||
      !features.calendar_export ||
      exportProblem(event, byId.get(event.work_order_id))
    )
      return;
    const controller = new AbortController();
    downloadController.current = controller;
    setDownloading(event.id);
    setNotice("");
    try {
      const file = await calendarFile(event.id, fetch, controller.signal);
      if (controller.signal.aborted) return;
      saveCalendar(file, event.id);
      setNotice(
        "日历文件已下载，请在自己的日历中确认导入。改期后需重新导入或手动更新。",
      );
    } catch (e) {
      if (controller.signal.aborted) return;
      setNotice(e instanceof Error ? e.message : "导出失败");
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        onSessionExpired();
      else void state.refresh();
    } finally {
      if (!controller.signal.aborted) setDownloading("");
    }
  }
  const shown =
    view === "agenda" ? sortedEvents(events) : eventsForDay(events, day);
  return (
    <section aria-label="日历与待办" className="planning-workspace">
      <div className="page-heading">
        <div>
          <p className="eyebrow">个人安排</p>
          <h1>日历与待办</h1>
          <p>所有时刻按香港时间显示；只有日期的安排保留原日期与时区。</p>
        </div>
        <button
          className="secondary"
          disabled={state.loading}
          onClick={() => void state.refresh()}
        >
          刷新安排
        </button>
      </div>
      {state.error && (
        <p className="notice stale" role="alert">
          {state.error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <div className="planning-grid">
        <div className="panel">
          <div className="segmented" aria-label="日历显示方式">
            {[
              ["month", "月历"],
              ["agenda", "全部安排"],
            ].map(([id, label]) => (
              <button
                className="secondary"
                key={id}
                aria-pressed={view === id}
                onClick={() => setView(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={history}
              onChange={(e) => setHistory(e.target.checked)}
            />
            显示已完成／取消工单的日历历史
          </label>
          {view === "month" && (
            <>
              <div className="month-toolbar">
                <button
                  className="secondary"
                  aria-label="上个月"
                  onClick={() => select(shiftMonth(month, -1) + "-01")}
                >
                  ‹
                </button>
                <h2>{month.replace("-", " 年 ")} 月</h2>
                <button
                  className="secondary"
                  aria-label="下个月"
                  onClick={() => select(shiftMonth(month, 1) + "-01")}
                >
                  ›
                </button>
                <button
                  className="secondary"
                  onClick={() => select(todayInHongKong())}
                >
                  今天
                </button>
              </div>
              <div className="month-weekdays" aria-hidden="true">
                {["一", "二", "三", "四", "五", "六", "日"].map((d) => (
                  <span key={d}>{d}</span>
                ))}
              </div>
              <div
                className="month-grid"
                role="group"
                aria-label="选择日期，可用方向键移动，Home／End 跳到本周首尾"
              >
                {monthDays(month).map((date) => {
                  const daily = eventsForDay(events, date);
                  return (
                    <button
                      key={date}
                      id={"calendar-day-" + date}
                      className={`calendar-day ${date.slice(0, 7) !== month ? "outside" : ""}`}
                      aria-pressed={date === day}
                      aria-label={`${date}，${daily.length} 项安排`}
                      tabIndex={
                        date === day ||
                        (day.slice(0, 7) !== month && date === month + "-01")
                          ? 0
                          : -1
                      }
                      onClick={() => select(date)}
                      onKeyDown={(e) => {
                        const weekday =
                          (new Date(date + "T12:00:00Z").getUTCDay() + 6) % 7;
                        const shifts: Record<string, number> = {
                          ArrowLeft: -1,
                          ArrowRight: 1,
                          ArrowUp: -7,
                          ArrowDown: 7,
                          Home: -weekday,
                          End: 6 - weekday,
                        };
                        if (e.key in shifts) {
                          e.preventDefault();
                          select(shiftDay(date, shifts[e.key]), true);
                        }
                      }}
                    >
                      <span>{Number(date.slice(-2))}</span>
                      {daily.length > 0 && <small>{daily.length} 项安排</small>}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          <h2>{view === "month" ? `${day} 的安排` : "全部安排"}</h2>
          {state.loading && <p role="status">正在核对最新安排…</p>}
          {!state.loading && !state.error && !shown.length && (
            <p className="empty">
              {state.data?.calendar.length
                ? "该范围没有安排，可切换日期或查看历史。"
                : "还没有日历安排。正式确认工单时间后会出现在这里。"}
            </p>
          )}
          {shown.map((event) => {
            const order = byId.get(event.work_order_id),
              problem = exportProblem(event, order);
            return (
              <article className="calendar-event" key={event.id}>
                <span className={`tag ${event.tentative ? "warning" : ""}`}>
                  {event.tentative ? "暂定" : "正式"}
                </span>
                <h3>{order?.summary ?? "工单不可用"}</h3>
                <p>{fieldValue(event.schedule)}</p>
                <small>
                  {order ? orderStates[order.status] : "待核对"} · 工单 v
                  {event.work_order_version} · 缓冲 {event.buffer_minutes} 分钟
                </small>
                {order?.fields.address.status === "confirmed" && (
                  <p>地点：{fieldValue(order.fields.address.value)}</p>
                )}
                <div className="approval-buttons">
                  <button
                    className="secondary"
                    disabled={!order}
                    onClick={() => onOpenOrder(event.work_order_id)}
                  >
                    查看工单
                  </button>
                  <button
                    disabled={
                      state.loading ||
                      !!downloading ||
                      !!problem ||
                      !features.calendar_export
                    }
                    onClick={() => void download(event)}
                  >
                    {downloading === event.id
                      ? "正在下载…"
                      : "加入我的日历 (.ics)"}
                  </button>
                </div>
                {(problem || !features.calendar_export) && (
                  <small>{problem || "当前后端尚未提供日历下载接口。"}</small>
                )}
              </article>
            );
          })}
          <p className="subtle">
            导出会下载包含业务标题、时间和已确认地址的文件。请妥善保存。手机／Google／Outlook
            日历由你自行导入，改期不会自动同步；重复导入可能产生重复安排。
          </p>
        </div>
        <aside className="panel">
          <h2>全部工单待办</h2>
          <label>
            待办范围
            <select
              value={taskFilter}
              onChange={(e) => setTaskFilter(e.target.value)}
            >
              <option value="active">待处理与受阻</option>
              <option value="all">全部历史</option>
            </select>
          </label>
          {tasks
            .filter(
              (t) =>
                taskFilter === "all" ||
                ["pending", "blocked"].includes(t.state),
            )
            .map((task) => (
              <article className="task" key={task.id}>
                <h3>{task.title}</h3>
                <span className="tag">{taskStates[task.state]}</span>
                <p>
                  {byId.get(task.work_order_id)?.summary ?? "关联工单不可用"}
                </p>
                <small>截止：{fieldValue(task.due)}</small>
                <small>
                  依赖：
                  {task.depends_on
                    .map(
                      (id) =>
                        tasks.find((t) => t.id === id)?.title ?? "未载入的待办",
                    )
                    .join("、") || "无"}
                </small>
                <button
                  className="secondary"
                  onClick={() => onOpenOrder(task.work_order_id)}
                >
                  查看相关工单
                </button>
              </article>
            ))}
          {state.data &&
            !tasks.some(
              (t) =>
                taskFilter === "all" ||
                ["pending", "blocked"].includes(t.state),
            ) && <p>该范围暂无待办。</p>}
          <p className="availability-note">
            待办会随已确认安排更新。手动完成／编辑待办的后端接口尚未提供，本版只读。
          </p>
        </aside>
      </div>
    </section>
  );
}
