import { useEffect, useMemo, useState } from "react";
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
import { instant } from "./work-order-view";
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
}: {
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
    [actionId, setActionId] = useState(""),
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
    [receipt, setReceipt] = useState<Model["WahaSendActionView"] | null>(null);
  const [tick, setTick] = useState(0),
    [checked, setChecked] = useState(0);
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
    expiresAt: checked + 10000,
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
        ? request<{ data: Model["ConnectorStatus"][] }>(
            "/connectors",
            undefined,
            a.signal,
          ).then((v) => v.data)
        : Promise.resolve([]),
    ])
      .then(([q, ac, c]) => {
        if (a.signal.aborted) return;
        if (ac.some((v) => v.account_id !== accountId))
          throw Error("草稿归属无法核对");
        setQueue(q);
        setActions(ac);
        setConnections(c);
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
            throw Error("来源范围无法核对");
          setMessages(ms);
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
    if (actionId)
      void api
        .read<Loop["ActionView"]>(`/actions/${actionId}`, a.signal)
        .then(async (v) => {
          if (v.account_id !== accountId || v.id !== actionId)
            throw Error("草稿归属无法核对");
          if (a.signal.aborted) return;
          setAction(v);
          setBody(v.body);
          setChecked(Date.now());
          if (connection && features.business_sending) {
            const prefix = `/connectors/${connection}`;
            const [s, p] = await Promise.all([
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
            ]);
            if (a.signal.aborted) return;
            if (s.data.connection_id !== connection)
              throw Error("连接归属无法核对");
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
                r.data.chat_id !== v.conversation_id ||
                r.data.work_order_id !== v.work_order_id ||
                r.data.payload.text !== v.body
              )
                throw Error("发送记录归属或正文不一致，不能使用此关联");
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
        <h2>归单与业务回复</h2>
        <button className="secondary" onClick={() => setTick((v) => v + 1)}>
          读取当前归单与回复
        </button>
      </div>
      {features.manual_assignment && (
        <details>
          <summary>人工归单</summary>
          <label>
            待复核消息
            <select value={job} onChange={(e) => setJob(e.target.value)}>
              <option value="">选择一条</option>
              {queue
                .filter((q) => q.context_version === q.current_context_version)
                .map((q) => (
                  <option key={q.id} value={q.id}>
                    会话 {q.conversation_id.slice(-6)} · {q.reason}
                  </option>
                ))}
            </select>
          </label>
          {selected && (
            <>
              <h3>当前原文</h3>
              {messages.map((m) => (
                <p className="message" key={m.id + ":" + m.revision}>
                  {m.revoked ? "已撤回" : m.text} <small>r{m.revision}</small>
                </p>
              ))}
              <label>
                归入工单
                <select
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="">选择已有开放工单</option>
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
                    {target && (
                      <LoopCommand
                        {...common}
                        label="核对归单"
                        intent={{
                          path: `/review-items/${job}/assign`,
                          body: {
                            action: "assign",
                            expected_context_version: context,
                            work_order_id: target,
                          } satisfies Loop["AssignMessageCommand"],
                          review: `将当前会话 v${context} 的这条消息归入“${orders.find((o) => o.id === target)?.summary}”，仅记录归属，不自动确认业务字段。`,
                        }}
                      />
                    )}
                    <LoopCommand
                      {...common}
                      label="标记无需归单"
                      intent={{
                        path: `/review-items/${job}/assign`,
                        body: {
                          action: "dismiss",
                          expected_context_version: context,
                          work_order_id: null,
                        },
                        review: `将当前会话 v${context} 的这条消息标记为无需归单，不创建工单，不发送回复。`,
                      }}
                    />
                  </>
                )}
            </>
          )}
        </details>
      )}
      <details>
        <summary>修改回复与发送记录</summary>
        <label>
          业务草稿
          <select
            value={actionId}
            onChange={(e) => setActionId(e.target.value)}
          >
            <option value="">选择草稿</option>
            {actions.map((a) => (
              <option key={a.id} value={a.id}>
                {orders.find((o) => o.id === a.work_order_id)?.summary ||
                  a.work_order_id.slice(-6)}{" "}
                · r{a.revision} · {a.state}
              </option>
            ))}
          </select>
        </label>
        {action && (
          <>
            <p>
              收件会话 {action.conversation_id.slice(-6)} · 有效至{" "}
              {instant(action.expires_at)}
            </p>
            <p className="reply-body">{action.body}</p>
            {action.state === "pending_approval" && (
              <>
                <label>
                  修改正文
                  <textarea
                    value={body}
                    maxLength={4096}
                    onChange={(e) => setBody(e.target.value)}
                  />
                </label>
                {body.trim() && body !== action.body && (
                  <LoopCommand
                    {...common}
                    label="核对修改草稿"
                    intent={{
                      path: `/actions/${action.id}/edit`,
                      body: {
                        body: body.trim(),
                        snapshot_hash: action.snapshot_hash,
                        expected_action_revision: action.revision,
                      } satisfies Loop["EditActionCommand"],
                      review: `修改发给会话 ${action.conversation_id.slice(-6)} 的第 ${action.revision} 版草稿，新正文：“${body.trim()}”。保存后生成新版本，仍需另行批准，不会发送。`,
                    }}
                  />
                )}
              </>
            )}
            {features.business_sending && (
              <>
                <label>
                  发送连接
                  <select
                    value={connection}
                    onChange={(e) => setConnection(e.target.value)}
                  >
                    <option value="">选择已授权连接</option>
                    {connections.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.id.slice(-6)}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  需先在 WhatsApp 连接页授权此会话发送；这里不会扩大授权范围。
                </p>
                {action.state === "approved" &&
                  Date.parse(action.expires_at) > Date.now() &&
                  setup?.enabled &&
                  setup.available &&
                  !setup.provider_sample_stale &&
                  permission?.enabled &&
                  permission.chat_ids.includes(action.conversation_id) &&
                  (!permission.expires_at ||
                    Date.parse(permission.expires_at) > Date.now()) && (
                    <LoopCommand
                      {...common}
                      label="核对并提交业务发送"
                      intent={{
                        path: `/actions/${action.id}/send`,
                        body: {
                          connection_id: connection,
                          expected_control_version: setup.control_version,
                          expected_permission_version: permission.version,
                          expected_action_revision: action.revision,
                          snapshot_hash: action.snapshot_hash,
                        } satisfies Loop["SendApprovedActionCommand"],
                        review: `把已批准草稿 r${action.revision} 交给连接 ${connection.slice(-6)}，收件会话 ${action.conversation_id.slice(-6)}，完整正文：“${action.body}”。连接 v${setup.control_version}／发送授权 v${permission.version}。提交不代表客户收到；结果未知时先核对，禁止另建发送。`,
                      }}
                    />
                  )}
                {receipt && (
                  <p role="status">
                    已通过当前账号核对关联回执：{receipt.state} ·{" "}
                    {receipt.delivery_status}
                    {receipt.error_code && ` · ${receipt.error_code}`}
                    。取消、对账或人工核查请到 WhatsApp 消息页选择此记录{" "}
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
