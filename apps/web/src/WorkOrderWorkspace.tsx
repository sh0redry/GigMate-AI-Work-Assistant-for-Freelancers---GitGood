import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { orderCommands } from "./order-command-api";
import { OrderLifecycle } from "./OrderLifecycle";
import { InspectOrderAttempt } from "./InspectOrderAttempt";
import { ReplyPanel } from "./ReplyPanel";
import { unavailableFeatures, type Features } from "./features";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { canConfirm, BusinessStore } from "./business-store";
import {
  changeContext,
  businessApi,
  workspaceApi,
  type Change,
  type BusinessSnapshot,
  type RequestApi,
} from "./workspace-api";
import {
  conflictLabel,
  customerStates,
  fieldNames,
  fieldValue,
  filterOrders,
  friendlyInstant,
  messageAnchor,
  onDay,
  orderStates,
  reviewBinding,
} from "./work-order-view";

type Props = {
  csrf: string;
  accountId?: string;
  features?: Features;
  initialSelected?: string;
  onSessionExpired: () => void;
  onBusyChange: (busy: boolean) => void;
  onOpenSend?: (actionId: string) => void;
  onConnect?: () => void;
  onOpenApprovals?: () => void;
  request?: RequestApi;
};
function snippet(text: string | null | undefined) {
  if (!text) return t("（没有文字）");
  return text.length > 24 ? text.slice(0, 24) + "…" : text;
}
function Sources({
  sources,
  data,
}: {
  sources: Change["sources"];
  data: BusinessSnapshot;
}) {
  const found = sources.flatMap((source) => {
    const message = data.messages.find(
      (m) =>
        m.id === source.message_id && m.revision === source.message_revision,
    );
    return message ? [message] : [];
  });
  if (!found.length)
    return sources.length ? (
      <small className="source-quote">
        {t("依据的消息暂时读不到，先别确认。")}
      </small>
    ) : null;
  return (
    <small className="source-quote">
      {t("依据：")}
      {found.map((message) => (
        <a
          key={`${message.id}-${message.revision}`}
          href={`#${messageAnchor(message.id, message.revision)}`}
        >
          {message.revoked
            ? t("已撤回的消息")
            : t("客人说「{0}」", snippet(message.text))}
        </a>
      ))}
    </small>
  );
}
export function WorkOrderWorkspace({
  csrf,
  accountId,
  features = unavailableFeatures,
  initialSelected = "",
  onSessionExpired,
  onBusyChange,
  onOpenSend,
  onConnect,
  onOpenApprovals,
  request,
}: Props) {
  const commands = useMemo(
    () => (accountId ? orderCommands(csrf, accountId) : undefined),
    [csrf, accountId],
  );
  const [recoverConsent, setRecoverConsent] = useState(false);
  const [commandError, setCommandError] = useState("");
  const [commandBusy, setCommandBusy] = useState(false);
  const store = useMemo(
    () =>
      new BusinessStore(
        businessApi(request ?? workspaceApi(csrf), commands),
        onSessionExpired,
      ),
    [csrf, onSessionExpired, request, commands],
  );
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [conversation, setConversation] = useState("all");
  const day = "";
  const [review, setReview] = useState<{ id: string; binding: string } | null>(
    null,
  );
  useEffect(() => {
    store.start();
    if (initialSelected) store.select(initialSelected);
    const timer = setInterval(() => {
      if (!document.hidden) store.poll();
    }, 5000);
    return () => {
      clearInterval(timer);
      store.dispose();
    };
  }, [store, initialSelected]);
  useEffect(() => {
    onBusyChange(state.mutating || commandBusy);
    return () => onBusyChange(false);
  }, [state.mutating, commandBusy, onBusyChange]);
  useEffect(() => {
    setConversation("all");
    setReview(null);
  }, [state.selected]);
  const data = state.data;
  const order = data?.orders.find((o) => o.id === state.selected);
  const detailReady = !!data && data.selected === state.selected;
  const ready = store.ready();
  const openOrder =
    !!order && !["cancelled", "completed"].includes(order.status);
  const recoveryBinding = JSON.stringify({
    attempt: commands?.attempt,
    data: state.data,
    stale: state.stale,
  });
  useEffect(() => setRecoverConsent(false), [recoveryBinding]);
  const orders = filterOrders(data?.orders ?? [], search, status);
  const changes = detailReady ? (data?.changes ?? []) : [];
  // Incomplete proposals (e.g. only a start time) still need the merchant's
  // attention, so they appear as a next step without a confirm button.
  const pending = changes.filter(
    (c) => c.status === "proposed" || c.status === "needs_review",
  );
  const reviewed = changes.find((c) => c.id === review?.id);
  const reviewCurrent =
    !!data && !!reviewed && review?.binding === reviewBinding(data, reviewed);
  const confirmable = (change: Change) =>
    !!data &&
    !!order &&
    ready &&
    !commandBusy &&
    !commands?.attempt &&
    !commands?.error &&
    openOrder &&
    (change.field !== "address" || features.address_confirmation) &&
    canConfirm(change, order.version, changeContext(data, change) ?? -1);
  const history = changes.filter(
    (c) => c.status !== "proposed" && c.status !== "needs_review",
  );
  const fieldOrder = [
    "schedule",
    "address",
    "specification",
    "quantity",
    "deadline",
  ] as const;
  const known = order
    ? fieldOrder.flatMap((name) => {
        const field = order.fields[name];
        return field && field.status !== "missing" ? [{ name, field }] : [];
      })
    : [];
  const missing = order
    ? fieldOrder
        .filter(
          (name) =>
            !order.fields[name] || order.fields[name]?.status === "missing",
        )
        .map((name) => fieldNames[name])
    : [];
  const tasks = detailReady
    ? (data?.tasks ?? []).filter(
        (t) =>
          t.work_order_id === state.selected &&
          ["pending", "blocked"].includes(t.state),
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
      {(commands?.error || commandError) && (
        <p role="alert" className="notice stale">
          {commands?.error || commandError}
        </p>
      )}
      {commands?.attempt && (
        <section className="panel review-panel" aria-label={t("核对原操作")}>
          <h2>{t("有一项原操作尚待核对")}</h2>
          <p>
            {commands.attempt.intent.kind === "create"
              ? t("新建工单")
              : commands.attempt.intent.kind === "status"
                ? t("修改工单状态")
                : t(
                    "确认{0}",
                    commands.attempt.intent.review.field === "address"
                      ? t("地址")
                      : t("时间安排"),
                  )}{" "}
            {t("· 请求编号")}
            {commands.attempt.key}
          </p>
          {commands.attempt.intent.kind === "create" ? (
            <>
              <p>
                {t("业务：")}
                {commands.attempt.intent.body.summary}
              </p>
              <p>
                {t("时间：")}
                {fieldValue(commands.attempt.intent.body.schedule)}
              </p>
              <p>
                {t("地址：")}
                {commands.attempt.intent.body.address ?? t("未提供")}
              </p>
              <small>
                {t("会话")}
                {commands.attempt.intent.body.conversation_id}
                {t("；时间原文")}{" "}
                {commands.attempt.intent.body.schedule_sources.length}{" "}
                {t("条；地址原文")}{" "}
                {commands.attempt.intent.body.address_sources.length} {t("条")}
              </small>
            </>
          ) : commands.attempt.intent.kind === "status" ? (
            <p>
              {t("原工单版本 v")}
              {commands.attempt.intent.body.expected_version} →{" "}
              {orderStates[commands.attempt.intent.body.status]}
            </p>
          ) : (
            <>
              <p>
                {t("业务：")}
                {commands.attempt.intent.review.summary}
              </p>
              <p>
                {fieldValue(commands.attempt.intent.review.oldValue)} →{" "}
                {fieldValue(commands.attempt.intent.review.newValue)}
              </p>
              <small>
                {t("原工单 v")}
                {commands.attempt.intent.body.expected_version}
                {t("；原会话 v")}
                {commands.attempt.intent.body.expected_context_version}
              </small>
              {commands.attempt.intent.review.sources.map((source) => (
                <small key={source.message_id}>
                  {t("原文编号")}
                  {source.message_id} · r{source.message_revision}
                </small>
              ))}
            </>
          )}
          <p>
            {t(
              "读取、刷新和重新登录不会重发。只有明确核对后，才使用相同编号、原内容与原版本核对操作；服务端仍会拒绝旧来源或版本。",
            )}
          </p>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={recoverConsent}
              onChange={(e) => setRecoverConsent(e.target.checked)}
            />
            {t("我已核对原内容和当前状态，继续核对原编号操作")}
          </label>
          <button
            disabled={
              !ready ||
              !recoverConsent ||
              commandBusy ||
              !!commands.error ||
              (commands.attempt.intent.kind === "create" &&
                !features.create_order) ||
              (commands.attempt.intent.kind === "status" &&
                !features.order_status)
            }
            onClick={() => {
              setCommandBusy(true);
              setCommandError("");
              void commands
                .retry()
                .then(() => store.refresh())
                .catch((e) => {
                  setCommandError(
                    e instanceof Error ? e.message : t("核对失败"),
                  );
                  if (e?.code === "UNAUTHENTICATED") onSessionExpired();
                })
                .finally(() => {
                  setCommandBusy(false);
                  setRecoverConsent(false);
                });
            }}
          >
            {t("核对原编号操作")}
          </button>
          <InspectOrderAttempt
            commands={commands}
            ready={ready}
            busy={commandBusy || state.mutating}
            onBusy={setCommandBusy}
            onDone={() => {
              setCommandError("");
              void store.refresh();
            }}
            onError={(e) => {
              setCommandError(e instanceof Error ? e.message : t("核对失败"));
              if ((e as { code?: string })?.code === "UNAUTHENTICATED")
                onSessionExpired();
            }}
          />
        </section>
      )}
      {(state.error || state.notice || (state.stale && data)) && (
        <div
          className={`notice ${state.stale && data ? "stale" : ""}`}
          role="status"
          aria-live="polite"
        >
          {state.error ? t(state.error) : state.notice ? t(state.notice) : ""}
          {state.stale && data && (
            <p>{t("网络不稳，下面是上次读到的内容，暂时不能确认。")}</p>
          )}
        </div>
      )}
      <div className="grid" aria-busy={state.loading || state.mutating}>
        <aside className="panel">
          <div className="row">
            <h2>{t("我的工单")}</h2>
            <button
              className="secondary small"
              disabled={state.loading || state.mutating}
              onClick={() => void store.refresh()}
            >
              {t("刷新")}
            </button>
          </div>
          <label>
            {t("搜索")}
            <input
              type="search"
              value={search}
              placeholder={t("客人或工作")}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label>
            {t("状态")}
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">{t("全部状态")}</option>
              {Object.entries(orderStates).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          {orders.map((item) => (
            <button
              key={item.id}
              className={`order ${item.id === state.selected ? "active" : ""}`}
              aria-pressed={item.id === state.selected}
              disabled={state.mutating || commandBusy}
              onClick={() => store.select(item.id)}
            >
              <strong>{item.summary}</strong>
              <small>
                {item.fields.schedule?.value
                  ? fieldValue(item.fields.schedule.value)
                  : t("时间未定")}
              </small>
              <small>{orderStates[item.status]}</small>
            </button>
          ))}
          {data && !orders.length && (
            <p>
              {data.orders.length
                ? t("没有符合条件的工单。")
                : t(
                    "还没有工单。先到「WhatsApp 连接」选好要处理的聊天，再点「新建工单」。",
                  )}
            </p>
          )}
          {!data && (
            <p>
              {state.loading
                ? t("正在读取工单…")
                : t("暂时读不到工单，请稍后刷新。")}
            </p>
          )}
        </aside>
        <section className="panel" aria-label={t("工单详情")}>
          {detailReady && !order && (
            <p className="empty">{t("在左边选一张工单。")}</p>
          )}
          {!detailReady && <p className="empty">{t("正在打开工单…")}</p>}
          {detailReady && order && data && (
            <>
              <div className="order-head">
                <h2>{order.summary}</h2>
                <span className="tag">{orderStates[order.status]}</span>
              </div>
              <section className="next-step" aria-label={t("下一步")}>
                <p className="eyebrow">{t("下一步")}</p>
                {pending.length === 0 && (
                  <h3>
                    {!openOrder
                      ? t("这张工单已经结束。")
                      : missing.length
                        ? t("还缺：{0}", missing.join("、"))
                        : t("都安排好了，没有要你处理的事。")}
                  </h3>
                )}
                {pending.map((change) => {
                  const context = changeContext(data, change);
                  const current =
                    context !== null &&
                    change.base_work_order_version === order.version &&
                    change.context_version === context;
                  const conflict = change.conflict_ids
                    .map((id) => conflictLabel(data, id))
                    .join("、");
                  const incomplete = change.status === "needs_review";
                  const ok = !incomplete && confirmable(change);
                  return (
                    <article className="change" key={change.id}>
                      <h3>
                        {incomplete
                          ? change.field === "schedule"
                            ? t("客人说了时间，但还不完整")
                            : t(
                                "客人提到的{0}需要你看一下",
                                fieldNames[change.field] ?? change.field,
                              )
                          : conflict
                            ? t("客人想改时间，但和「{0}」撞了", conflict)
                            : t(
                                "客人提了新的{0}",
                                fieldNames[change.field] ?? change.field,
                              )}
                      </h3>
                      <p className="change-values">
                        <span className="old">
                          {fieldValue(change.old_value)}
                        </span>
                        <span aria-hidden="true">→</span>
                        <strong>{fieldValue(change.new_value)}</strong>
                      </p>
                      {change.customer_confirmation !== "not_requested" && (
                        <p className="subtle">
                          {customerStates[change.customer_confirmation]}
                        </p>
                      )}
                      <Sources sources={change.sources} data={data} />
                      {incomplete && (
                        <p className="subtle">
                          {change.field === "schedule"
                            ? t(
                                "还不知道几点结束（或要多久），先问客人，问清楚后才能放进日历。",
                              )
                            : t("意思不够明确，先和客人确认一下。")}
                        </p>
                      )}
                      {["schedule", "address"].includes(change.field) &&
                        !conflict &&
                        !incomplete && (
                          <div className="reply-actions">
                            <button
                              disabled={!ok}
                              onClick={() =>
                                setReview({
                                  id: change.id,
                                  binding: reviewBinding(data, change),
                                })
                              }
                            >
                              {change.field === "address"
                                ? t("确认新地址")
                                : t("确认新时间")}
                            </button>
                          </div>
                        )}
                      {!ok && !conflict && !incomplete && (
                        <p className="subtle">
                          {!current
                            ? t(
                                "聊天、授权或工单已变化，这条旧提议不能直接确认。",
                              )
                            : !openOrder
                              ? t("工单已结束，不能再改。")
                              : change.field === "address" &&
                                  !features.address_confirmation
                                ? t("地址确认功能还没开放。")
                                : t("请稍等，正在同步最新内容。")}
                        </p>
                      )}
                      {!["schedule", "address"].includes(change.field) && (
                        <p className="subtle">
                          {t("这类内容请到「业务管理」的需求与交付里确认。")}
                        </p>
                      )}
                      {review?.id === change.id && (
                        <div className="confirm-sheet" role="region">
                          {reviewCurrent && reviewed ? (
                            <>
                              <p>
                                {t(
                                  "确认后，「{0}」改为 {1}。日历和准备待办会一起更新。",
                                  order.summary,
                                  fieldValue(reviewed.new_value),
                                )}
                              </p>
                              {reviewed.customer_confirmation !==
                                "confirmed" && (
                                <p className="subtle">
                                  {t(
                                    "客人还没明确答应，会先记成「暂定」，等客人确认后再变正式。",
                                  )}
                                </p>
                              )}
                            </>
                          ) : (
                            <p>{t("内容刚更新了，请重新看一眼再确认。")}</p>
                          )}
                          <div className="reply-actions">
                            <button
                              disabled={
                                !reviewCurrent ||
                                !reviewed ||
                                !confirmable(reviewed)
                              }
                              onClick={() => {
                                if (reviewed && reviewCurrent) {
                                  void store.confirm(reviewed.id);
                                  setReview(null);
                                }
                              }}
                            >
                              {t("确认")}
                            </button>
                            <button
                              className="secondary"
                              disabled={state.mutating || commandBusy}
                              onClick={() => setReview(null)}
                            >
                              {t("先不")}
                            </button>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
                {accountId && openOrder && (
                  <ReplyPanel
                    csrf={csrf}
                    accountId={accountId}
                    orderId={order.id}
                    orderSummary={order.summary}
                    features={features}
                    refreshKey={state.updatedAt}
                    onOpenSend={onOpenSend}
                    onConnect={onConnect}
                    onOpenApprovals={onOpenApprovals}
                    onSessionExpired={onSessionExpired}
                  />
                )}
              </section>
              <h3 className="section-title">{t("安排")}</h3>
              <dl className="order-facts">
                {known.map(({ name, field }) => (
                  <div key={name}>
                    <dt>{fieldNames[name]}</dt>
                    <dd>
                      {fieldValue(field.value)}{" "}
                      {field.status !== "confirmed" && (
                        <span className="tag warning">
                          {field.status === "proposed"
                            ? t("等客人确认")
                            : t("需要你看一下")}
                        </span>
                      )}
                    </dd>
                  </div>
                ))}
                {missing.length > 0 && (
                  <div>
                    <dt>{t("还没有")}</dt>
                    <dd className="subtle">{missing.join("、")}</dd>
                  </div>
                )}
              </dl>
              {history.length > 0 && (
                <details className="quiet">
                  <summary>{t("改动记录（{0}）", history.length)}</summary>
                  {history.map((change) => (
                    <p key={change.id} className="subtle">
                      {fieldNames[change.field]}：{fieldValue(change.old_value)}{" "}
                      → {fieldValue(change.new_value)} ·{" "}
                      {change.status === "confirmed"
                        ? t("已确认")
                        : t("已过时")}
                    </p>
                  ))}
                </details>
              )}
              <details className="quiet" open>
                <summary>{t("聊天记录")}</summary>
                {order.conversation_ids.length > 1 && (
                  <label>
                    {t("显示聊天")}
                    <select
                      value={conversation}
                      onChange={(e) => setConversation(e.target.value)}
                    >
                      <option value="all">{t("全部")}</option>
                      {order.conversation_ids.map((id, index) => (
                        <option value={id} key={id}>
                          {t("聊天 {0}", index + 1)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {data.messages
                  .filter(
                    (m) =>
                      conversation === "all" ||
                      m.conversation_id === conversation,
                  )
                  .map((message) => (
                    <div
                      className={`message ${message.direction === "incoming" ? "" : "mine"}`}
                      id={messageAnchor(message.id, message.revision)}
                      key={`${message.id}-${message.revision}`}
                    >
                      <small>
                        {message.direction === "incoming" ? t("客人") : t("我")}{" "}
                        · {friendlyInstant(message.occurred_at)}
                      </small>
                      <p>
                        {message.revoked
                          ? t("（这条消息已撤回）")
                          : (message.text ?? t("（没有文字）"))}
                      </p>
                    </div>
                  ))}
                {!data.messages.length && (
                  <p className="subtle">{t("还没有聊天记录。")}</p>
                )}
              </details>
              {commands && (
                <details className="quiet">
                  <summary>{t("更多操作（开始、完成、取消工单）")}</summary>
                  <OrderLifecycle
                    order={order}
                    enabled={features.order_status}
                    ready={ready && !state.mutating}
                    commands={commands}
                    onBusyChange={setCommandBusy}
                    onDone={() => void store.refresh()}
                    onError={(e) => {
                      setCommandError(
                        e instanceof Error ? e.message : t("操作失败"),
                      );
                      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
                        onSessionExpired();
                    }}
                  />
                </details>
              )}
            </>
          )}
        </section>
        <aside className="panel">
          <h2>{t("我的日程")}</h2>
          {calendar.map((event) => (
            <div
              className={`calendar ${event.work_order_id === state.selected ? "current" : ""}`}
              key={event.id}
            >
              <strong>{fieldValue(event.schedule)}</strong>
              <span>
                {data?.orders.find((o) => o.id === event.work_order_id)
                  ?.summary ?? t("未命名工单")}
                {event.tentative && (
                  <span className="tag warning">{t("暂定")}</span>
                )}
              </span>
            </div>
          ))}
          {data && !calendar.length && (
            <p className="subtle">{t("还没有安排。")}</p>
          )}
          <h2>{t("这张工单要做的事")}</h2>
          {tasks.map((task) => (
            <div className="task" key={task.id}>
              <strong>{task.title}</strong>
              <small>
                {task.due ? t("截止 {0}", fieldValue(task.due)) : ""}
                {task.state === "blocked" && ` · ${t("要等前一件事做完")}`}
              </small>
            </div>
          ))}
          {detailReady && !tasks.length && (
            <p className="subtle">{t("暂时没有要做的事。")}</p>
          )}
        </aside>
      </div>
    </>
  );
}
