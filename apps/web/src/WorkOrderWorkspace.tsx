import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  canConfirm,
  changePresentation,
  ReplayStore,
  SAMPLE_ORDER_ID,
} from "./replay-store";
import {
  changeContext,
  replayApi,
  workspaceApi,
  type Change,
  type ReplaySnapshot,
  type RequestApi,
} from "./workspace-api";
import {
  conflictLabel,
  customerStates,
  fieldNames,
  fieldStates,
  fieldValue,
  filterOrders,
  instant,
  messageAnchor,
  onDay,
  orderStates,
  reviewBinding,
  taskStates,
} from "./work-order-view";

type Props = {
  csrf: string;
  username: string;
  onSessionExpired: () => void;
  onBusyChange: (busy: boolean) => void;
  mode?: "business" | "replay";
  request?: RequestApi;
};
function Sources({
  sources,
  data,
}: {
  sources: Change["sources"];
  data: ReplaySnapshot;
}) {
  return (
    <small>
      来源：
      {!sources.length
        ? "未提供原文依据"
        : sources.map((source) => {
            const message = data.messages.find(
              (m) =>
                m.id === source.message_id &&
                m.revision === source.message_revision,
            );
            const label = `${source.message_id.slice(-6)} · r${source.message_revision}`;
            return (
              <span
                className="source-reference"
                key={`${source.message_id}-${source.message_revision}`}
              >
                {message ? (
                  <a href={`#${messageAnchor(message.id, message.revision)}`}>
                    {label}
                  </a>
                ) : (
                  `${label}（该版本未载入，需复核）`
                )}
              </span>
            );
          })}
    </small>
  );
}
export function WorkOrderWorkspace({
  csrf,
  username,
  onSessionExpired,
  onBusyChange,
  mode = "business",
  request,
}: Props) {
  const store = useMemo(
    () =>
      new ReplayStore(
        replayApi(request ?? workspaceApi(csrf)),
        onSessionExpired,
      ),
    [csrf, onSessionExpired, request],
  );
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [conversation, setConversation] = useState("all");
  const [taskFilter, setTaskFilter] = useState("active");
  const [day, setDay] = useState("");
  const [review, setReview] = useState<{ id: string; binding: string } | null>(
    null,
  );
  const [consent, setConsent] = useState(false);
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
  useEffect(() => {
    setConversation("all");
    setReview(null);
    setConsent(false);
  }, [state.selected]);
  const data = state.data;
  const order = data?.orders.find((o) => o.id === state.selected);
  const detailReady = !!data && data.selected === state.selected;
  const ready = store.ready();
  const openOrder =
    !!order && !["cancelled", "completed"].includes(order.status);
  const orders = filterOrders(data?.orders ?? [], search, status);
  const changes = detailReady ? (data?.changes ?? []) : [];
  const pending = changes.filter((c) => c.status === "proposed");
  const reviewed = changes.find((c) => c.id === review?.id);
  const reviewCurrent =
    !!data && !!reviewed && review?.binding === reviewBinding(data, reviewed);
  const reviewedContext =
    data && reviewed ? changeContext(data, reviewed) : null;
  const confirmable = (change: Change) =>
    !!data &&
    !!order &&
    ready &&
    openOrder &&
    canConfirm(change, order.version, changeContext(data, change) ?? -1);
  const tasks = detailReady
    ? (data?.tasks ?? []).filter(
        (t) =>
          t.work_order_id === state.selected &&
          (taskFilter === "all" || ["pending", "blocked"].includes(t.state)),
      )
    : [];
  const calendar = (data?.calendar ?? [])
    .filter((e) => !day || onDay(e, day))
    .sort((a, b) => {
      const key = (e: typeof a) =>
        e.schedule.kind === "date_only"
          ? `${e.schedule.date}T00:00:00+08:00`
          : e.schedule.start_at;
      return (
        Date.parse(key(a)) - Date.parse(key(b)) || a.id.localeCompare(b.id)
      );
    });
  return (
    <>
      <div
        className={`notice ${state.stale && data ? "stale" : ""}`}
        role="status"
        aria-live="polite"
      >
        {state.error ||
          state.notice ||
          "顾客提议、顾客确认和商户确认分别显示。未知地址保持未提供。"}
        {state.stale && data && <p>下面是上次读取的数据，当前不能据此确认。</p>}
      </div>
      <div className="replay-tools">
        <small>
          {state.loading
            ? "正在读取最新数据…"
            : state.updatedAt
              ? `最近读取：${instant(new Date(state.updatedAt).toISOString())}`
              : "尚未读取数据"}
        </small>
        <button
          className="secondary"
          disabled={state.loading || state.mutating}
          onClick={() => void store.refresh()}
        >
          刷新{mode === "replay" ? "回放" : "业务"}数据
        </button>
      </div>
      <div className="grid" aria-busy={state.loading || state.mutating}>
        <aside className="panel">
          <h2>工单列表</h2>
          <label>
            搜索业务
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label>
            工单状态
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">全部状态</option>
              {Object.entries(orderStates).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <small>
            显示 {orders.length} / {data?.orders.length ?? 0} 张工单
          </small>
          {order && !orders.some((o) => o.id === order.id) && (
            <p>筛选隐藏了当前工单；右侧仍显示「{order.summary}」。</p>
          )}
          {orders.map((item) => (
            <button
              key={item.id}
              className={`order ${item.id === state.selected ? "active" : ""}`}
              aria-pressed={item.id === state.selected}
              disabled={state.mutating}
              onClick={() => store.select(item.id)}
            >
              <strong>{item.summary}</strong>
              <small>
                版本 {item.version} · {orderStates[item.status]} ·{" "}
                {item.conversation_ids.length} 个关联会话
              </small>
            </button>
          ))}
          {data && !orders.length && (
            <p>
              {data.orders.length
                ? "没有匹配的工单，调整搜索或状态筛选。"
                : "当前账号没有工单。新建工单接口尚未实现，请在开发环境使用虚构回放样例。"}
            </p>
          )}
          {!data && (
            <p>
              {state.loading ? "正在读取工单…" : "读取失败，请检查服务后刷新。"}
            </p>
          )}
          {mode === "replay" && (
            <section aria-label="合成回放输入">
              <h3>虚构回放输入</h3>
              <p>
                固定样例只适用于 merchant 的「虚构业务预约」，不会发送消息。
              </p>
              <button
                className="secondary"
                disabled={
                  !ready ||
                  username !== "merchant" ||
                  state.selected !== SAMPLE_ORDER_ID
                }
                onClick={() => void store.replay("reschedule", username)}
              >
                回放：15:00 冲突改期
              </button>
              <button
                disabled={
                  !ready ||
                  username !== "merchant" ||
                  state.selected !== SAMPLE_ORDER_ID
                }
                onClick={() => void store.replay("available", username)}
              >
                回放：16:30 可用时段
              </button>
              <small>重复输入不会重复创建记录。刷新不会重置数据。</small>
            </section>
          )}
        </aside>
        <main className="panel">
          <h2>工单详情</h2>
          {!detailReady && <p>正在核对选中工单，完成前不能确认。</p>}
          {detailReady && order && data && (
            <>
              <div className="confirmed">
                <h3>{order.summary}</h3>
                <small>
                  {orderStates[order.status]} · 版本 {order.version} · 更新于{" "}
                  {instant(order.updated_at)}
                </small>
                {(["schedule", "address"] as const).map((name) => (
                  <div className="business-field" key={name}>
                    <strong>
                      {fieldNames[name]}：{fieldValue(order.fields[name].value)}
                    </strong>
                    <span
                      className={`tag ${order.fields[name].status !== "confirmed" ? "warning" : ""}`}
                    >
                      {fieldStates[order.fields[name].status]}
                    </span>
                    <Sources sources={order.fields[name].sources} data={data} />
                    {order.fields[name].interpretation && (
                      <small>解释：{order.fields[name].interpretation}</small>
                    )}
                  </div>
                ))}
              </div>
              <h2>
                待核对变更 <span className="tag">{pending.length} 项提议</span>
              </h2>
              {!changes.length && (
                <p className="empty">
                  暂无变更提议。真实消息的通用提取仍取决于后端能力；可在工单回放页验证固定样例。
                </p>
              )}
              {changes.map((change) => {
                const context = changeContext(data, change);
                const current =
                  context !== null &&
                  change.base_work_order_version === order.version &&
                  change.context_version === context;
                const display = changePresentation(change, current);
                return (
                  <article className="change" key={change.id}>
                    <div className="row">
                      <h3>{fieldNames[change.field]}变更</h3>
                      <span
                        className={`tag ${display.warning ? "warning" : ""}`}
                      >
                        {display.label}
                      </span>
                    </div>
                    <p>原值：{fieldValue(change.old_value)}</p>
                    <p>
                      <strong>提议值：{fieldValue(change.new_value)}</strong>
                    </p>
                    <small>
                      {change.proposer === "customer" ? "顾客提出" : "商户提出"}{" "}
                      · {customerStates[change.customer_confirmation]} ·
                      工单基于 v{change.base_work_order_version} / 会话 v
                      {change.context_version}
                    </small>
                    <Sources sources={change.sources} data={data} />
                    {change.conflict_ids.length > 0 && (
                      <p>
                        冲突安排：
                        {change.conflict_ids
                          .map((id) => conflictLabel(data, id))
                          .join("、")}
                      </p>
                    )}
                    <p>
                      {context === null
                        ? "来源版本或归属无法完整核对，保持待复核。"
                        : change.field !== "schedule"
                          ? "当前接口仅支持时间安排确认，此字段保持待核对。"
                          : display.text}
                    </p>
                    {change.field === "schedule" && (
                      <button
                        disabled={!confirmable(change)}
                        onClick={() => {
                          setReview({
                            id: change.id,
                            binding: reviewBinding(data, change),
                          });
                          setConsent(false);
                        }}
                      >
                        核对并确认安排
                      </button>
                    )}
                  </article>
                );
              })}
              {review && (
                <section
                  className="change review-panel"
                  role="region"
                  aria-label="确认安排复核"
                >
                  <h3>复核本次正式更新</h3>
                  {reviewCurrent && reviewed ? (
                    <>
                      <p>
                        「{order.summary}」：{fieldValue(reviewed.old_value)} →{" "}
                        {fieldValue(reviewed.new_value)}
                      </p>
                      <Sources sources={reviewed.sources} data={data} />
                      <small>
                        工单 v{order.version} · 来源会话 v{reviewedContext}
                      </small>
                    </>
                  ) : (
                    <p>
                      提议、工单或来源已变化，本次复核失效。关闭后重新核对。
                    </p>
                  )}
                  <label className="inline-check">
                    <input
                      type="checkbox"
                      checked={consent}
                      disabled={
                        !reviewCurrent || !reviewed || !confirmable(reviewed)
                      }
                      onChange={(e) => setConsent(e.target.checked)}
                    />
                    我已核对，确认更新工单、同步正式日历、取消旧自动待办并生成新的准备事项。
                  </label>
                  <button
                    disabled={
                      !consent ||
                      !reviewCurrent ||
                      !reviewed ||
                      !confirmable(reviewed)
                    }
                    onClick={() => {
                      if (reviewed && reviewCurrent) {
                        void store.confirm(reviewed.id);
                        setReview(null);
                        setConsent(false);
                      }
                    }}
                  >
                    确认并同步安排
                  </button>{" "}
                  <button
                    className="secondary"
                    disabled={state.mutating}
                    onClick={() => {
                      setReview(null);
                      setConsent(false);
                    }}
                  >
                    关闭复核
                  </button>
                </section>
              )}
              <h2>关联会话与来源时间线</h2>
              <label>
                显示会话
                <select
                  value={conversation}
                  onChange={(e) => setConversation(e.target.value)}
                >
                  <option value="all">
                    全部关联会话（{order.conversation_ids.length}）
                  </option>
                  {order.conversation_ids.map((id, index) => (
                    <option value={id} key={id}>
                      会话 {index + 1} · {id.slice(-6)} · v
                      {data.contexts?.[id] ?? data.contextVersion}
                    </option>
                  ))}
                </select>
              </label>
              {data.messages
                .filter(
                  (m) =>
                    conversation === "all" ||
                    m.conversation_id === conversation,
                )
                .map((message) => (
                  <div
                    className="message"
                    id={messageAnchor(message.id, message.revision)}
                    key={`${message.id}-${message.revision}`}
                  >
                    <small>
                      {message.direction === "incoming" ? "顾客" : "商户"} ·{" "}
                      {message.source} · 会话{" "}
                      {message.conversation_id.slice(-6)} ·{" "}
                      {message.id.slice(-6)} · r{message.revision} ·{" "}
                      {instant(message.occurred_at)}
                    </small>
                    <p>
                      {message.revoked
                        ? "消息已撤回，相关内容需复核"
                        : (message.text ?? "没有可读取文字")}
                    </p>
                  </div>
                ))}
              {!data.messages.some(
                (m) =>
                  conversation === "all" || m.conversation_id === conversation,
              ) && <p>该范围暂无来源消息。</p>}
              {conversation !== "all" && (
                <small>来源链接可能指向隐藏会话；选择全部关联会话查看。</small>
              )}
            </>
          )}
        </main>
        <aside className="panel">
          <h2>个人日历</h2>
          <small>账号全部安排；时刻按香港时区显示，全天日期保留原时区。</small>
          <label>
            查看日期
            <input
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          {day && (
            <button className="secondary" onClick={() => setDay("")}>
              查看全部安排
            </button>
          )}
          {calendar.map((event) => (
            <div className="calendar" key={event.id}>
              <span>
                {event.tentative ? "暂定" : "正式"} ·{" "}
                {event.work_order_id === state.selected
                  ? "当前工单"
                  : "其他工单"}
              </span>
              <strong>
                {data?.orders.find((o) => o.id === event.work_order_id)
                  ?.summary ?? "未提供工单标题"}
              </strong>
              <p>{fieldValue(event.schedule)}</p>
              <small>
                工单 v{event.work_order_version} · 缓冲 {event.buffer_minutes}{" "}
                分钟
              </small>
            </div>
          ))}
          {data && !calendar.length && <p>该范围暂无日历安排。</p>}
          <h2>当前工单待办</h2>
          <label>
            待办范围
            <select
              value={taskFilter}
              onChange={(e) => setTaskFilter(e.target.value)}
            >
              <option value="active">待处理与受阻</option>
              <option value="all">全部（含历史）</option>
            </select>
          </label>
          {tasks.map((task) => (
            <div className="task" key={task.id}>
              <strong>{task.title}</strong>
              <small>
                {taskStates[task.state]} · 工单 v{task.work_order_version}
              </small>
              <small>截止：{fieldValue(task.due)}</small>
              <small>
                依赖：
                {task.depends_on.length
                  ? task.depends_on
                      .map(
                        (id) =>
                          data?.tasks.find((t) => t.id === id)?.title ??
                          `${id.slice(-6)}（未载入）`,
                      )
                      .join("、")
                  : "无"}
              </small>
              {data && <Sources sources={task.sources} data={data} />}
            </div>
          ))}
          {detailReady && !tasks.length && <p>当前工单在该范围暂无待办。</p>}
          <small>
            新建、工单状态修改、回复审批和外发属于后续模块；当前页面不会发送消息。
          </small>
        </aside>
      </div>
    </>
  );
}
