import { t, localized } from "./i18n.ts";
import { actionStates, deliveryStates } from "./approval-view";
import { useStableState as useState } from "./useStableState";
import { useEffect, useMemo } from "react";
import { LoopCommand } from "./LoopCommand";
import type { LoopApi, Loop } from "./business-loop-api";
import {
  allPages,
  workspaceApi,
  type Detail,
  type Order,
  type Message,
} from "./workspace-api";
import type { Features } from "./features";
import type { components } from "./generated/api";
import { instant, reviewReasons } from "./work-order-view";
import {
  byTime,
  contactLabel,
  loadContactLabels,
  shortTime,
} from "./contact-label";
const sendStates: Record<string, string> = localized({
  queued: "已批准，排队中",
  preparing: "连接检查中",
  dispatching: "提交中，不能取消",
  accepted: "WAHA 已接受",
  failed: "未提交成功",
  cancelled: "已取消",
  result_unknown: "结果未知，禁止重发",
});
type Model = components["schemas"];
export function BusinessLoopReview({
  api,
  csrf,
  accountId,
  features,
  orders,
  onDone,
  onError,
  onBusy,
  initialActionId = "",
}: {
  initialActionId?: string;
  api: LoopApi;
  csrf: string;
  accountId: string;
  features: Features;
  orders: Order[];
  onDone: () => void;
  onError: (e: unknown) => void;
  onBusy: (v: boolean) => void;
}) {
  const request = useMemo(() => workspaceApi(csrf), [csrf]);
  const [queue, setQueue] = useState<Model["ReviewItem"][]>([]),
    [job, setJob] = useState(""),
    [target, setTarget] = useState(""),
    [messages, setMessages] = useState<Message[]>([]),
    [context, setContext] = useState(0);
  const [actions, setActions] = useState<Loop["ActionView"][]>([]),
    [actionId, setActionId] = useState(initialActionId),
    [action, setAction] = useState<Loop["ActionView"] | null>(null),
    [body, setBody] = useState("");
  const [connections, setConnections] = useState<Model["ConnectorStatus"][]>(
      [],
    ),
    [connection, setConnection] = useState(""),
    [setup, setSetup] = useState<Model["WahaSetup"] | null>(null),
    [permission, setPermission] = useState<
      Model["WahaSendPermissionView"] | null
    >(null),
    [chatId, setChatId] = useState(""),
    [receipt, setReceipt] = useState<Model["WahaSendActionView"] | null>(null);
  const [tick, setTick] = useState(0),
    [checked, setChecked] = useState(0),
    [contacts, setContacts] = useState<Map<string, string>>(new Map());
  const contact = (conversationId: string) =>
    contacts.get(conversationId) ?? contactLabel(undefined);
  const done = () => {
    setTick((v) => v + 1);
    onDone();
  };
  const common = {
    api,
    onDone: done,
    onError,
    onBusy,
    disabled: !checked,
    expiresAt: checked + 300000,
  };
  useEffect(() => {
    const a = new AbortController();
    setChecked(0);
    void Promise.all([
      features.manual_assignment
        ? allPages<Model["ReviewItem"]>(request, "/review-items", a.signal)
        : Promise.resolve([]),
      allPages<Loop["ActionView"]>(request, "/actions", a.signal),
      features.business_sending
        ? allPages<Model["ConnectorStatus"]>(request, "/connectors", a.signal)
        : Promise.resolve([]),
      loadContactLabels(request, a.signal),
    ])
      .then(([q, ac, c, labels]) => {
        if (a.signal.aborted) return;
        if (ac.some((v) => v.account_id !== accountId))
          throw Error(t("草稿归属无法核对"));
        setQueue(
          [...q].sort(byTime<Model["ReviewItem"]>((i) => i.observed_at)),
        );
        setContacts(labels);
        setActions(ac);
        setConnections(c);
        if (c.length === 1) setConnection((v) => v || c[0].id);
      })
      .catch((e) => {
        if (!a.signal.aborted) onError(e);
      });
    return () => a.abort();
  }, [request, accountId, features, tick, onError]);
  const selected = queue.find((q) => q.id === job);
  useEffect(() => {
    const a = new AbortController();
    setMessages([]);
    setContext(0);
    setTarget("");
    if (selected)
      void Promise.all([
        allPages<Message>(
          request,
          `/conversations/${selected.conversation_id}/messages`,
          a.signal,
        ),
        request<Detail<Model["Conversation"]>>(
          `/conversations/${selected.conversation_id}`,
          undefined,
          a.signal,
        ),
      ])
        .then(([ms, c]) => {
          if (a.signal.aborted) return;
          if (
            c.data.id !== selected.conversation_id ||
            ms.some((m) => m.conversation_id !== c.data.id)
          )
            throw Error(t("来源范围无法核对"));
          setMessages([...ms].sort(byTime<Message>((m) => m.occurred_at)));
          setContext(c.data.context_version);
          setChecked(Date.now());
        })
        .catch((e) => {
          if (!a.signal.aborted) onError(e);
        });
    return () => a.abort();
  }, [request, selected, tick, onError]);
  useEffect(() => {
    const a = new AbortController();
    setAction(null);
    setBody("");
    setSetup(null);
    setPermission(null);
    setReceipt(null);
    setChatId("");
    if (actionId)
      void api
        .read<Loop["ActionView"]>(`/actions/${actionId}`, a.signal)
        .then(async (v) => {
          if (v.account_id !== accountId || v.id !== actionId)
            throw Error(t("草稿归属无法核对"));
          if (a.signal.aborted) return;
          setAction(v);
          setBody(v.body);
          setChecked(Date.now());
          if (connection && features.business_sending) {
            const prefix = `/connectors/${connection}`;
            const [s, p, chats] = await Promise.all([
              request<Detail<Model["WahaSetup"]>>(
                `${prefix}/setup`,
                undefined,
                a.signal,
              ),
              request<Detail<Model["WahaSendPermissionView"]>>(
                `${prefix}/sending/permission`,
                undefined,
                a.signal,
              ),
              request<Detail<Model["WahaChoice"][]>>(
                `${prefix}/chats`,
                undefined,
                a.signal,
              ),
            ]);
            if (a.signal.aborted) return;
            if (s.data.connection_id !== connection)
              throw Error(t("连接归属无法核对"));
            const matches = chats.data.filter(
              (c) => c.selected && c.conversation_id === v.conversation_id,
            );
            if (matches.length !== 1)
              throw Error(
                t("所选连接没有唯一对应的已授权聊天，请回连接页核对。"),
              );
            const linkedChat = matches[0].id;
            setChatId(linkedChat);
            setSetup(s.data);
            setPermission(p.data);
            if (v.send_action_id) {
              const r = await request<Detail<Model["WahaSendActionView"]>>(
                `${prefix}/sending/actions/${encodeURIComponent(v.send_action_id)}`,
                undefined,
                a.signal,
              );
              if (a.signal.aborted) return;
              if (
                r.data.id !== v.send_action_id ||
                r.data.chat_id !== linkedChat ||
                r.data.work_order_id !== v.work_order_id ||
                r.data.payload.text !== v.body
              )
                throw Error(t("发送记录归属或正文不一致，不能使用此关联"));
              setReceipt(r.data);
            }
          }
        })
        .catch((e) => {
          if (!a.signal.aborted) {
            setChecked(0);
            onError(e);
          }
        });
    return () => a.abort();
  }, [
    actionId,
    connection,
    api,
    request,
    features.business_sending,
    accountId,
    tick,
    onError,
  ]);
  return (
    <section className="panel">
      <div className="page-heading">
        <h2>{t("归单与业务回复")}</h2>
        <button className="secondary" onClick={() => setTick((v) => v + 1)}>
          {t("读取当前归单与回复")}
        </button>
      </div>
      {features.manual_assignment && (
        <details>
          <summary>{t("人工归单")}</summary>
          <label>
            {t("待复核消息")}
            <select value={job} onChange={(e) => setJob(e.target.value)}>
              <option value="">{t("选择一条")}</option>
              {queue
                .filter((q) => q.context_version === q.current_context_version)
                .map((q) => (
                  <option key={q.id} value={q.id}>
                    {contact(q.conversation_id)} · {shortTime(q.observed_at)} ·{" "}
                    {reviewReasons[q.reason] ?? t("需要人工核对")}
                  </option>
                ))}
            </select>
          </label>
          {selected && (
            <>
              {selected.reason === "MODEL_OUTCOME_UNKNOWN" && (
                <p className="notice warning">
                  {t(
                    "模型调用结果未知。保留原编号供维护者核查，不重新归单调用；可核对原文后手动处理或标记忽略。",
                  )}
                  {selected.model_request_id}
                </p>
              )}
              <h3>{t("当前原文")}</h3>
              {messages.map((m) => (
                <p className="message" key={m.id + ":" + m.revision}>
                  {m.revoked ? t("已撤回") : m.text}{" "}
                  <small>r{m.revision}</small>
                </p>
              ))}
              <label>
                {t("归入工单")}
                <select
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="">{t("选择已有开放工单")}</option>
                  {orders
                    .filter(
                      (o) =>
                        o.conversation_ids.includes(selected.conversation_id) &&
                        !["completed", "cancelled"].includes(o.status),
                    )
                    .map((o) => (
                      <option value={o.id} key={o.id}>
                        {o.summary}
                      </option>
                    ))}
                </select>
              </label>
              {context === selected.context_version &&
                messages.some(
                  (m) => m.id === selected.message_id && !m.revoked,
                ) && (
                  <>
                    {target && selected.reason !== "MODEL_OUTCOME_UNKNOWN" && (
                      <LoopCommand
                        {...common}
                        label={t("核对归单")}
                        intent={{
                          path: `/review-items/${job}/assign`,
                          body: {
                            action: "assign",
                            expected_context_version: context,
                            work_order_id: target,
                          } satisfies Loop["AssignMessageCommand"],
                          review: t(
                            "将当前会话 v{0} 的这条消息归入“{1}”，仅记录归属，不自动确认业务字段。",
                            context,
                            orders.find((o) => o.id === target)?.summary,
                          ),
                        }}
                      />
                    )}
                    <LoopCommand
                      {...common}
                      label={t("标记无需归单")}
                      intent={{
                        path: `/review-items/${job}/assign`,
                        body: {
                          action: "dismiss",
                          expected_context_version: context,
                          work_order_id: null,
                        },
                        review: t(
                          "将当前会话 v{0} 的这条消息标记为无需归单，不创建工单，不发送回复。",
                          context,
                        ),
                      }}
                    />
                  </>
                )}
            </>
          )}
        </details>
      )}
      <details open={!!initialActionId} id="send-replies">
        <summary>{t("发送已批准的回复")}</summary>
        <label>
          {t("业务草稿")}
          <select
            value={actionId}
            onChange={(e) => setActionId(e.target.value)}
          >
            <option value="">{t("选择草稿")}</option>
            {actions.map((a) => (
              <option key={a.id} value={a.id}>
                {orders.find((o) => o.id === a.work_order_id)?.summary ||
                  a.work_order_id.slice(-6)}{" "}
                · r{a.revision} · {actionStates[a.state] ?? t("需要人工核对")}
              </option>
            ))}
          </select>
        </label>
        {action && (
          <>
            <p>
              {t("收件会话")} {contact(action.conversation_id)} {t("· 有效至")}{" "}
              {instant(action.expires_at)}
            </p>
            <p className="reply-body">{action.body}</p>
            {action.state === "pending_approval" && (
              <>
                <label>
                  {t("修改正文")}
                  <textarea
                    value={body}
                    maxLength={4096}
                    onChange={(e) => setBody(e.target.value)}
                  />
                </label>
                {body.trim() && body !== action.body && (
                  <LoopCommand
                    {...common}
                    label={t("核对修改草稿")}
                    intent={{
                      path: `/actions/${action.id}/edit`,
                      body: {
                        body: body.trim(),
                        snapshot_hash: action.snapshot_hash,
                        expected_action_revision: action.revision,
                      } satisfies Loop["EditActionCommand"],
                      review: t(
                        "修改发给会话 {0} 的第 {1} 版草稿，新正文：“{2}”。保存后生成新版本，仍需另行批准，不会发送。",
                        contact(action.conversation_id),
                        action.revision,
                        body.trim(),
                      ),
                    }}
                  />
                )}
              </>
            )}
            {features.business_sending && (
              <>
                <label>
                  {t("发送连接")}
                  <select
                    value={connection}
                    onChange={(e) => setConnection(e.target.value)}
                  >
                    <option value="">{t("选择要用的 WhatsApp")}</option>
                    {connections.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.id.slice(-6)}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  {t(
                    "需先在 WhatsApp 连接页授权此会话发送；这里不会扩大授权范围。",
                  )}
                </p>
                {action.state === "approved" &&
                  Date.parse(action.expires_at) > Date.now() &&
                  setup?.enabled &&
                  setup.available &&
                  !setup.provider_sample_stale &&
                  permission?.enabled &&
                  chatId &&
                  permission.chat_ids.includes(chatId) &&
                  (!permission.expires_at ||
                    Date.parse(permission.expires_at) > Date.now()) && (
                    <LoopCommand
                      {...common}
                      label={t("发送给客人")}
                      confirmLabel={t("确认发送")}
                      intent={{
                        path: `/actions/${action.id}/send`,
                        body: {
                          connection_id: connection,
                          expected_control_version: setup.control_version,
                          expected_permission_version: permission.version,
                          expected_action_revision: action.revision,
                          snapshot_hash: action.snapshot_hash,
                        } satisfies Loop["SendApprovedActionCommand"],
                        review: t(
                          "把已批准草稿 r{0} 交给连接 {1}，收件会话 {2}，完整正文：“{3}”。连接 v{4}／发送授权 v{5}。提交不代表客户收到；结果未知时先核对，禁止另建发送。",
                          action.revision,
                          connection.slice(-6),
                          contact(action.conversation_id),
                          action.body,
                          setup.control_version,
                          permission.version,
                        ),
                      }}
                    />
                  )}
                {receipt && (
                  <p role="status">
                    {t("已通过当前账号核对关联回执：")}
                    {sendStates[receipt.state] ?? t("需要人工核对")} ·{" "}
                    {deliveryStates[receipt.delivery_status] ??
                      t("需要人工核对")}
                    {receipt.error_code &&
                      ` · ${reviewReasons[receipt.error_code] ?? t("处理失败，需要核对原文")}`}
                    {t("。取消、对账或人工核查请到 WhatsApp 消息页选择此记录")}{" "}
                    {receipt.id.slice(-6)}。
                  </p>
                )}
              </>
            )}
          </>
        )}
      </details>
    </section>
  );
}
