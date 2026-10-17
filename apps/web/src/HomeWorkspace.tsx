import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { useCallback, useEffect, useMemo } from "react";
import {
  allPages,
  workspaceApi,
  type Calendar,
  type Message,
  type Order,
  type RequestApi,
  type Task,
} from "./workspace-api";
import type { Action, Conversation } from "./approvals-api";
import type { Loop } from "./business-loop-api";
import { triggerDescription } from "./approval-view";
import { fieldValue, friendlyInstant, onDay } from "./work-order-view";
import { loopReady, unavailableFeatures, type Features } from "./features";
import { ReplyPanel } from "./ReplyPanel";

type Connector = Loop["ConnectorStatus"];
type Summary = Loop["DailySummary"];

export type HomeView =
  | "business"
  | "approvals"
  | "planning"
  | "connect"
  | "create"
  | "management";

type Props = {
  csrf: string;
  accountId: string;
  features?: Features;
  onSessionExpired: () => void;
  onNavigate: (view: HomeView) => void;
  onOpenOrder: (id: string) => void;
  onOpenSend: (actionId: string) => void;
  request?: RequestApi;
};

/** Everything the home page reads, loaded together so the widgets agree. */
export type HomeData = {
  orders: Order[];
  actions: Action[];
  calendar: Calendar[];
  tasks: Task[];
  conversations: Conversation[];
  connectors: Connector[] | null;
  summary: Summary | null;
  latest: { message: Message; orderId: string | null }[];
};

const CLOSED = ["completed", "cancelled"];
const HK = "Asia/Hong_Kong";

/** Calendar date (YYYY-MM-DD) in Hong Kong, `offset` days from now. */
export function hongKongDay(offset = 0, now = Date.now()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: HK,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(now + offset * 86400000));
}

function weekdayLabel(day: string) {
  const index = new Date(`${day}T12:00:00Z`).getUTCDay();
  return [t("日"), t("一"), t("二"), t("三"), t("四"), t("五"), t("六")][index];
}

function startOf(event: Calendar) {
  return event.schedule.kind === "date_only"
    ? Date.parse(`${event.schedule.date}T00:00:00+08:00`)
    : Date.parse(event.schedule.start_at);
}

/** Load the home data. Optional sources (connectors, summary, messages) never block the page. */
export async function loadHome(
  request: RequestApi,
  features: Features,
  signal: AbortSignal,
): Promise<HomeData> {
  const optional = <T,>(promise: Promise<T>, fallback: T) =>
    promise.catch((error) => {
      if (error?.code === "UNAUTHENTICATED") throw error;
      return fallback;
    });
  const [orders, actions, calendar, tasks, conversations, connectors, summary] =
    await Promise.all([
      allPages<Order>(request, "/work-orders", signal),
      allPages<Action>(request, "/actions", signal),
      allPages<Calendar>(request, "/calendar-events", signal),
      allPages<Task>(request, "/tasks", signal),
      optional(allPages<Conversation>(request, "/conversations", signal), []),
      optional<Connector[] | null>(
        allPages<Connector>(request, "/connectors", signal),
        null,
      ),
      loopReady(features)
        ? optional<Summary | null>(
            request<{ data: Summary }>(
              "/daily-summary",
              undefined,
              signal,
            ).then((r) => r.data),
            null,
          )
        : Promise.resolve(null),
    ]);
  // Latest customer messages: read the few conversations linked to open orders.
  const open = new Set(
    orders.filter((o) => !CLOSED.includes(o.status)).map((o) => o.id),
  );
  const watched = conversations
    .filter((c) => c.work_order_ids.some((id) => open.has(id)))
    .slice(0, 5);
  const threads = await Promise.all(
    watched.map((c) =>
      optional(
        allPages<Message>(
          request,
          `/conversations/${encodeURIComponent(c.id)}/messages`,
          signal,
        ),
        [],
      ).then((messages) =>
        messages.map((message) => ({
          message,
          orderId: c.work_order_ids.find((id) => open.has(id)) ?? null,
        })),
      ),
    ),
  );
  const latest = threads
    .flat()
    .filter(
      (m) =>
        m.message.direction === "incoming" &&
        !m.message.revoked &&
        m.message.text,
    )
    .sort((a, b) => b.message.occurred_at.localeCompare(a.message.occurred_at))
    .slice(0, 3);
  return {
    orders,
    actions,
    calendar,
    tasks,
    conversations,
    connectors,
    summary,
    latest,
  };
}

/** One line of the "needs you" list. */
type Attention = {
  key: string;
  orderId: string;
  title: string;
  detail: string;
  tone: "warn" | "info";
  action: { label: string; run: () => void };
};

export function HomeWorkspace({
  csrf,
  accountId,
  features = unavailableFeatures,
  onSessionExpired,
  onNavigate,
  onOpenOrder,
  onOpenSend,
  request,
}: Props) {
  const api = useMemo(() => request ?? workspaceApi(csrf), [request, csrf]);
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((v) => v + 1), []);

  useEffect(() => {
    const abort = new AbortController();
    loadHome(api, features, abort.signal)
      .then((next) => {
        if (abort.signal.aborted) return;
        setData(next);
        setError("");
      })
      .catch((e) => {
        if (abort.signal.aborted) return;
        if (e?.code === "UNAUTHENTICATED") onSessionExpired();
        else
          setError(
            e instanceof Error
              ? e.message
              : t("暂时读不到工作台数据，请稍后刷新。"),
          );
      });
    return () => abort.abort();
  }, [api, features, tick, onSessionExpired]);

  // Re-read every 15 seconds while the tab is visible, like the other workspaces.
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) refresh();
    }, 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!data)
    return (
      <section className="home" aria-label={t("今日")}>
        <HomeHeader count={null} />
        <p className={error ? "notice stale" : "home-loading"} role="status">
          {error || t("正在读取今天的工作…")}
        </p>
        {error && (
          <button className="secondary" onClick={refresh}>
            {t("重试")}
          </button>
        )}
      </section>
    );

  const orderName = (id: string | null) =>
    data.orders.find((o) => o.id === id)?.summary ?? t("未命名工单");
  const openOrders = data.orders.filter((o) => !CLOSED.includes(o.status));
  const waiting = openOrders.filter(
    (o) => o.status === "waiting_customer",
  ).length;
  const toApprove = data.actions.filter((a) => a.state === "pending_approval");
  const toSend = data.actions.filter(
    (a) => a.state === "approved" && a.delivery_status === "not_submitted",
  );

  // ---- "Needs you": replies to approve, replies to send, proposals to check ----
  const attention: Attention[] = [];
  const seen = new Set<string>();
  for (const a of toApprove) {
    seen.add(a.work_order_id);
    attention.push({
      key: a.id,
      orderId: a.work_order_id,
      title: orderName(a.work_order_id),
      detail: triggerDescription(a.trigger, a.open_items),
      tone: a.trigger.startsWith("schedule_conflict") ? "warn" : "info",
      action: { label: t("去处理"), run: () => onOpenOrder(a.work_order_id) },
    });
  }
  for (const a of toSend) {
    seen.add(a.work_order_id);
    attention.push({
      key: a.id,
      orderId: a.work_order_id,
      title: orderName(a.work_order_id),
      detail: t("回复已批准，还没发给客人"),
      tone: "info",
      action: { label: t("发送"), run: () => onOpenSend(a.id) },
    });
  }
  for (const o of openOrders) {
    if (seen.has(o.id) || !o.pending_change_ids.length) continue;
    seen.add(o.id);
    attention.push({
      key: o.id,
      orderId: o.id,
      title: o.summary,
      detail: t("客人提了新的安排，等你确认"),
      tone: "info",
      action: { label: t("查看"), run: () => onOpenOrder(o.id) },
    });
  }
  for (const entry of data.summary?.needs_decision ?? []) {
    if (!entry.work_order_id || seen.has(entry.work_order_id)) continue;
    seen.add(entry.work_order_id);
    attention.push({
      key: `summary-${entry.work_order_id}`,
      orderId: entry.work_order_id,
      title: orderName(entry.work_order_id),
      detail: t("有一项需要你决定"),
      tone: "info",
      action: {
        label: t("查看"),
        run: () => onOpenOrder(entry.work_order_id!),
      },
    });
  }
  const lead = toApprove[0];

  // ---- Schedule ----
  const today = hongKongDay();
  const todays = data.calendar
    .filter((e) => onDay(e, today))
    .sort((a, b) => startOf(a) - startOf(b));
  const next = todays.find(
    (e) =>
      e.schedule.kind === "date_only" ||
      Date.parse(e.schedule.end_at) > Date.now(),
  );
  const days = Array.from({ length: 7 }, (_, i) => hongKongDay(i));
  const perDay = days.map(
    (day) => data.calendar.filter((e) => onDay(e, day)).length,
  );
  const busiest = Math.max(1, ...perDay);

  // ---- Completion ----
  const counted = data.orders.filter((o) => o.status !== "cancelled");
  const done = counted.filter((o) => o.status === "completed").length;
  const percent = counted.length
    ? Math.round((done / counted.length) * 100)
    : 0;

  // ---- To-dos due today or overdue ----
  const endOfToday = Date.parse(`${today}T23:59:59+08:00`);
  const dueAt = (task: Task) =>
    !task.due
      ? Infinity
      : task.due.kind === "date_only"
        ? Date.parse(`${task.due.date}T23:59:59+08:00`)
        : Date.parse(task.due.at);
  const todos = data.tasks
    .filter(
      (task) =>
        ["pending", "blocked"].includes(task.state) &&
        dueAt(task) <= endOfToday,
    )
    .sort((a, b) => dueAt(a) - dueAt(b));

  // ---- WhatsApp ----
  const connector = data.connectors?.[0] ?? null;
  const connected = !!connector?.live_connected;

  return (
    <section className="home" aria-label={t("今日")}>
      <HomeHeader count={attention.length} onRefresh={refresh} />
      {error && (
        <p className="notice stale" role="status">
          {t("网络不稳，下面是上次读到的内容。")}
        </p>
      )}

      <div className="home-grid">
        {/* ① Large: everything that needs the merchant */}
        <article className="home-widget size-large">
          <div className="w-head">
            <p className="w-label">{t("需要你处理")}</p>
            {attention.length > 0 && (
              <span className="w-pill warn">
                {t("{0} 项", attention.length)}
              </span>
            )}
          </div>
          {!attention.length && (
            <div className="w-empty">
              <p className="w-big-text">{t("都处理完了")}</p>
              <p className="w-sub">
                {t("客人有新消息时，要你做决定的事会出现在这里。")}
              </p>
            </div>
          )}
          {lead && (
            <div className="w-lead">
              <p className="w-lead-title">{orderName(lead.work_order_id)}</p>
              <ReplyPanel
                csrf={csrf}
                accountId={accountId}
                orderId={lead.work_order_id}
                orderSummary={orderName(lead.work_order_id)}
                features={features}
                refreshKey={tick}
                onOpenSend={onOpenSend}
                onConnect={() => onNavigate("connect")}
                onOpenApprovals={() => onNavigate("approvals")}
                onSessionExpired={onSessionExpired}
              />
            </div>
          )}
          <ul className="w-list">
            {attention
              .filter((item) => item.key !== lead?.id)
              .slice(0, lead ? 3 : 5)
              .map((item) => (
                <li key={item.key}>
                  <div>
                    <p className="w-row-title">{item.title}</p>
                    <p
                      className={`w-sub ${item.tone === "warn" ? "warn-text" : ""}`}
                    >
                      {item.detail}
                    </p>
                  </div>
                  <button className="w-chip" onClick={item.action.run}>
                    {item.action.label}
                  </button>
                </li>
              ))}
          </ul>
          <button className="w-link" onClick={() => onNavigate("business")}>
            {t("查看全部工单 ›")}
          </button>
        </article>

        {/* ② Small: open orders */}
        <article className="home-widget">
          <p className="w-label">{t("进行中工单")}</p>
          <div>
            <p className="w-number">{openOrders.length}</p>
            <p className="w-sub">
              {waiting
                ? t("其中 {0} 张在等客人", waiting)
                : t("没有在等客人的工单")}
            </p>
          </div>
        </article>

        {/* ③ Small: replies */}
        <article className="home-widget">
          <p className="w-label">{t("待回复")}</p>
          <div>
            <p
              className={`w-number ${toApprove.length + toSend.length ? "warn-text" : ""}`}
            >
              {toApprove.length + toSend.length}
            </p>
            <p className="w-sub">
              {toSend.length
                ? t("{0} 条已批准、未发送", toSend.length)
                : t("批准后才会发给客人")}
            </p>
          </div>
        </article>

        {/* ④ Small: today's appointments */}
        <article className="home-widget">
          <p className="w-label">{t("今日预约")}</p>
          <div>
            <p className="w-number">{todays.length}</p>
            <p className="w-sub">
              {next
                ? t(
                    "下一个：{0} {1}",
                    fieldValue(next.schedule),
                    orderName(next.work_order_id),
                  )
                : t("今天没有预约")}
            </p>
          </div>
        </article>

        {/* ⑤ Small: completion ring */}
        <article className="home-widget">
          <p className="w-label">{t("已完成工单")}</p>
          <div className="w-ring-row">
            <svg
              width="72"
              height="72"
              viewBox="0 0 36 36"
              className="w-ring"
              aria-hidden="true"
            >
              <circle cx="18" cy="18" r="15.5" className="w-ring-track" />
              {percent > 0 && (
                <circle
                  cx="18"
                  cy="18"
                  r="15.5"
                  className="w-ring-bar"
                  pathLength={100}
                  strokeDasharray={`${percent} 100`}
                />
              )}
            </svg>
            <div>
              <p className="w-mid-number">{percent}%</p>
              <p className="w-sub">{t("{0} / {1} 张", done, counted.length)}</p>
            </div>
          </div>
        </article>

        {/* ⑥ Medium: appointments over the next 7 days */}
        <article className="home-widget size-wide">
          <div className="w-head">
            <div>
              <p className="w-label">{t("未来 7 天预约")}</p>
              <p className="w-mid-number">
                {perDay.reduce((a, b) => a + b, 0)}
              </p>
            </div>
            <button className="w-link" onClick={() => onNavigate("planning")}>
              {t("打开日历 ›")}
            </button>
          </div>
          <div
            className="w-bars"
            role="img"
            aria-label={days
              .map((day, i) => t("{0} {1} 个", weekdayLabel(day), perDay[i]))
              .join("，")}
          >
            {days.map((day, i) => (
              <div key={day} className={i === 0 ? "today" : ""}>
                <span className="w-bar-value">{perDay[i] || ""}</span>
                <span
                  className="w-bar"
                  style={{
                    height: `${Math.max(6, (perDay[i] / busiest) * 100)}%`,
                  }}
                />
                <span className="w-bar-label">
                  {i === 0 ? t("今天") : weekdayLabel(day)}
                </span>
              </div>
            ))}
          </div>
        </article>

        {/* ⑦ Medium: to-dos due today */}
        <article className="home-widget size-wide">
          <div className="w-head">
            <p className="w-label">{t("今天要做")}</p>
            <p className="w-sub">{t("{0} 项", todos.length)}</p>
          </div>
          {!todos.length && (
            <p className="w-sub">{t("今天没有到期的待办。")}</p>
          )}
          <ul className="w-list compact">
            {todos.slice(0, 4).map((task) => (
              <li key={task.id}>
                <button
                  className="w-row-button"
                  onClick={() => onOpenOrder(task.work_order_id)}
                >
                  <span
                    className={`w-dot ${dueAt(task) < Date.now() ? "warn" : ""}`}
                    aria-hidden="true"
                  />
                  <span className="w-row-title">{task.title}</span>
                  <span className="w-sub">
                    {task.state === "blocked"
                      ? t("要等前一件事")
                      : dueAt(task) < Date.now()
                        ? t("已逾期")
                        : fieldValue(task.due)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </article>

        {/* ⑧ Medium: latest customer messages */}
        <article className="home-widget size-wide">
          <div className="w-head">
            <p className="w-label">{t("客人最新消息")}</p>
          </div>
          {!data.latest.length && (
            <p className="w-sub">{t("已授权的工作聊天里还没有客人消息。")}</p>
          )}
          <ul className="w-list compact">
            {data.latest.map(({ message, orderId }) => (
              <li key={`${message.id}-${message.revision}`}>
                <button
                  className="w-row-button"
                  disabled={!orderId}
                  onClick={() => orderId && onOpenOrder(orderId)}
                >
                  <span className="w-avatar" aria-hidden="true">
                    {orderName(orderId).slice(0, 1)}
                  </span>
                  <span className="w-msg">
                    <span className="w-row-title">{orderName(orderId)}</span>
                    <span className="w-sub w-truncate">{message.text}</span>
                  </span>
                  <span className="w-sub">
                    {friendlyInstant(message.occurred_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </article>

        {/* ⑨ Small: shortcuts */}
        <article className="home-widget">
          <p className="w-label">{t("快捷入口")}</p>
          <div className="w-apps">
            {features.create_order && (
              <button onClick={() => onNavigate("create")}>
                <span className="w-app blue" aria-hidden="true">
                  ＋
                </span>
                {t("新建工单")}
              </button>
            )}
            <button onClick={() => onNavigate("approvals")}>
              <span className="w-app orange" aria-hidden="true">
                ✉
              </span>
              {t("回复审批")}
            </button>
            <button onClick={() => onNavigate("planning")}>
              <span className="w-app red" aria-hidden="true">
                ▦
              </span>
              {t("日程")}
            </button>
            <button onClick={() => onNavigate("connect")}>
              <span className="w-app green" aria-hidden="true">
                ⌁
              </span>
              {t("连接")}
            </button>
          </div>
        </article>

        {/* ⑩ Small: WhatsApp */}
        <article className="home-widget">
          <div className="w-head">
            <p className="w-label">WhatsApp</p>
            <span className={`w-status ${connected ? "ok" : ""}`}>
              {connected ? t("已连接") : connector ? t("未连接") : t("未设置")}
            </span>
          </div>
          <div>
            <p className="w-number">{data.conversations.length}</p>
            <p className="w-sub">{t("个聊天已授权处理")}</p>
            {!connected && (
              <button className="w-link" onClick={() => onNavigate("connect")}>
                {t("去连接 ›")}
              </button>
            )}
          </div>
        </article>
      </div>
    </section>
  );
}

function HomeHeader({
  count,
  onRefresh,
}: {
  count: number | null;
  onRefresh?: () => void;
}) {
  return (
    <div className="home-head">
      <div>
        <p className="w-label">
          {friendlyInstant(new Date().toISOString()).replace(
            /\s?\d{2}:\d{2}$/,
            "",
          )}
        </p>
        <h1>{t("今日")}</h1>
        {count !== null && (
          <p className="w-sub">
            {count
              ? t("有 {0} 件事等你处理。", count)
              : t("今天没有要你处理的事。")}
          </p>
        )}
      </div>
      {onRefresh && (
        <button className="secondary" onClick={onRefresh}>
          {t("刷新")}
        </button>
      )}
    </div>
  );
}
