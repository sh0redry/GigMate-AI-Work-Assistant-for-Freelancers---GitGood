import { useEffect, useMemo, useSyncExternalStore } from "react";
import {
  canConfirm,
  changePresentation,
  ReplayStore,
  SAMPLE_ORDER_ID,
} from "./replay-store";
import { replayApi, workspaceApi } from "./workspace-api";

function instant(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    timeZone: "Asia/Hong_Kong",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
function schedule(value: unknown): string {
  if (!value || typeof value !== "object") return "未提供";
  const item = value as {
    kind: string;
    start_at?: string;
    end_at?: string;
    date?: string;
  };
  if (item.kind === "date_only") return `${item.date} 全天`;
  return item.start_at && item.end_at
    ? `${instant(item.start_at)} → ${instant(item.end_at)}`
    : "待核对";
}
const taskStates = {
  pending: "待处理",
  blocked: "受阻",
  completed: "已完成",
  cancelled: "已取消",
};
const orderStates = {
  proposed: "待确认",
  confirmed: "已确认",
  in_progress: "进行中",
  completed: "已完成",
  cancelled: "已取消",
};

export function ReplayWorkspace({
  csrf,
  username,
  onSessionExpired,
  onBusyChange,
}: {
  csrf: string;
  username: string;
  onSessionExpired: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const store = useMemo(
    () => new ReplayStore(replayApi(workspaceApi(csrf)), onSessionExpired),
    [csrf, onSessionExpired],
  );
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  useEffect(() => {
    store.start();
    const timer = setInterval(() => store.poll(), 1500);
    return () => {
      clearInterval(timer);
      store.dispose();
    };
  }, [store]);
  useEffect(() => {
    onBusyChange(state.mutating);
    return () => onBusyChange(false);
  }, [state.mutating, onBusyChange]);
  const data = state.data;
  const order = data?.orders.find((o) => o.id === state.selected);
  const detailReady = data?.selected === state.selected;
  const ready = store.ready();
  const replayAllowed =
    ready && username === "merchant" && state.selected === SAMPLE_ORDER_ID;
  const openOrder = order && !["cancelled", "completed"].includes(order.status);

  return (
    <>
      <div
        className={`notice ${state.stale && data ? "stale" : ""}`}
        role="status"
        aria-live="polite"
      >
        {state.error ||
          state.notice ||
          "所有时间以香港时区显示。顾客提议不会自动覆盖正式安排。"}
        {state.stale && data && (
          <p>下面保留的是上次读取的数据，暂不能据此确认或回放。</p>
        )}
      </div>
      <div className="replay-tools">
        <small>
          {state.loading
            ? "正在读取最新数据…"
            : state.updatedAt
              ? `最近读取：${instant(new Date(state.updatedAt).toISOString())}（香港时间）`
              : "尚未读取数据"}
        </small>
        <button
          className="secondary"
          disabled={state.loading || state.mutating}
          onClick={() => void store.refresh()}
        >
          刷新回放数据
        </button>
      </div>
      <div className="grid" aria-busy={state.loading || state.mutating}>
        <aside className="panel">
          <h2>业务列表</h2>
          {data?.orders.map((item) => (
            <button
              key={item.id}
              className={`order ${state.selected === item.id ? "active" : ""}`}
              aria-pressed={state.selected === item.id}
              disabled={state.mutating}
              onClick={() => store.select(item.id)}
            >
              <strong>{item.summary}</strong>
              <small>
                版本 {item.version} ·{" "}
                {orderStates[item.status as keyof typeof orderStates] ??
                  item.status}
              </small>
            </button>
          ))}
          {data && !data.orders.length && (
            <p>
              当前服务没有回放工单。请打开已加载虚构样例的回放环境，再刷新。
            </p>
          )}
          {!data && (
            <p>
              {state.loading
                ? "正在读取业务列表…"
                : "暂时无法读取业务列表，请刷新重试。"}
            </p>
          )}
          <h3>回放输入</h3>
          <p>
            以下两条固定样例仅用于「虚构业务预约」。先等冲突提议出现，再回放可用时段。
          </p>
          {username === "merchant" &&
            state.selected &&
            state.selected !== SAMPLE_ORDER_ID && (
              <p>请先选择「虚构业务预约」再回放。</p>
            )}
          {username !== "merchant" && (
            <p>
              此账号可查看自己的业务，固定回放输入仅供 merchant 演示账号使用。
            </p>
          )}
          <button
            className="secondary"
            disabled={!replayAllowed}
            onClick={() => void store.replay("reschedule", username)}
          >
            回放：15:00 冲突改期
          </button>
          <button
            disabled={!replayAllowed}
            onClick={() => void store.replay("available", username)}
          >
            回放：16:30 可用时段
          </button>
          <small>
            重复输入不会重复创建记录。回放结果保存在本地数据库，刷新不会重置。
          </small>
        </aside>
        <main className="panel">
          <h2>待核对的业务变化</h2>
          {!detailReady && <p>正在读取选中业务，核对完成前不能确认。</p>}
          {detailReady && order && (
            <div className="confirmed">
              <small>
                当前正式安排 · 业务版本 {order.version} · 会话版本{" "}
                {data?.contextVersion}
              </small>
              <strong>{schedule(order.fields.schedule.value)}</strong>
              <span>
                地址：
                {order.fields.address.value === null
                  ? "未提供"
                  : String(order.fields.address.value)}
              </span>
            </div>
          )}
          {detailReady && data && (
            <>
              {!data.changes.length && (
                <p className="empty">
                  还没有变更提议。回放一条消息后，后台会生成带原文依据的提议。
                </p>
              )}
              {data.changes.map((change) => {
                const current =
                  !!order &&
                  change.base_work_order_version === order.version &&
                  change.context_version === data.contextVersion;
                const display = changePresentation(change, current);
                return (
                  <article className="change" key={change.id}>
                    <div className="row">
                      <h3>改期提议</h3>
                      <span
                        className={`tag ${display.warning ? "warning" : ""}`}
                      >
                        {display.label}
                      </span>
                    </div>
                    <p>原安排：{schedule(change.old_value)}</p>
                    <p>
                      <strong>新提议：{schedule(change.new_value)}</strong>
                    </p>
                    <small>
                      来源消息：
                      {change.sources.map((source, i) => (
                        <span
                          key={`${source.message_id}-${source.message_revision}`}
                        >
                          {i > 0 ? ", " : ""}
                          <a href={`#message-${source.message_id}`}>
                            {source.message_id.slice(-4)} · r
                            {source.message_revision}
                          </a>
                        </span>
                      ))}
                    </small>
                    <p>{display.text}</p>
                    <button
                      disabled={
                        !ready ||
                        !openOrder ||
                        !order ||
                        !canConfirm(change, order.version, data.contextVersion)
                      }
                      onClick={() => void store.confirm(change.id)}
                    >
                      确认并同步安排
                    </button>
                  </article>
                );
              })}
              <h2>来源时间线</h2>
              {!data.messages.length && <p>暂无来源消息。</p>}
              {data.messages.map((message) => (
                <div
                  className="message"
                  id={`message-${message.id}`}
                  key={message.id}
                >
                  <small>
                    {message.direction === "incoming" ? "顾客" : "商户"} ·{" "}
                    {message.source} · {message.id.slice(-4)} · r
                    {message.revision} · {instant(message.occurred_at)}
                  </small>
                  <p>
                    {message.revoked
                      ? "消息已撤回，相关内容需要复核"
                      : message.text}
                  </p>
                </div>
              ))}
            </>
          )}
        </main>
        <aside className="panel">
          <h2>个人安排</h2>
          {data?.calendar.map((event) => (
            <div className="calendar" key={event.id}>
              <span>
                {event.work_order_id === state.selected
                  ? "当前业务"
                  : "其他业务"}
              </span>
              <strong>{schedule(event.schedule)}</strong>
            </div>
          ))}
          {data && !data.calendar.length && <p>暂无个人安排。</p>}
          <h2>待办事项</h2>
          {data?.tasks
            .filter((task) => task.work_order_id === state.selected)
            .map((task) => (
              <div className="task" key={task.id}>
                <strong>{task.title}</strong>
                <small>
                  {taskStates[task.state]} · 业务版本 {task.work_order_version}
                </small>
                <small>
                  截止：
                  {task.due?.kind === "instant"
                    ? instant(task.due.at)
                    : task.due?.kind === "date_only"
                      ? task.due.date
                      : "未提供"}
                </small>
              </div>
            ))}
          {data &&
            !data.tasks.some(
              (task) => task.work_order_id === state.selected,
            ) && <p>当前业务暂无待办。</p>}
        </aside>
      </div>
    </>
  );
}
