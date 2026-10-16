import { useCallback, useEffect, useMemo, useState } from "react";
import {
  businessLoopApi,
  type Loop,
  type LoopOrder,
} from "./business-loop-api";
import { BusinessLoopReview } from "./BusinessLoopReview";
import { LoopCommand } from "./LoopCommand";
import { loopReady, type Features } from "./features";
import {
  allPages,
  workspaceApi,
  type Order,
  type Message,
  type Change,
  type Detail,
} from "./workspace-api";
import {
  fieldNames,
  fieldValue,
  instant,
  orderStates,
} from "./work-order-view";
import type { components } from "./generated/api";

type Props = {
  csrf: string;
  accountId: string;
  features: Features;
  onSessionExpired: () => void;
  onBusyChange: (value: boolean) => void;
  onOpenOrder: (id: string) => void;
};
export function BusinessLoopWorkspace(props: Props) {
  if (!loopReady(props.features)) return null;
  return <BusinessLoopContent {...props} />;
}
function BusinessLoopContent({
  csrf,
  accountId,
  features,
  onSessionExpired,
  onBusyChange,
  onOpenOrder,
}: Props) {
  const api = useMemo(
    () => businessLoopApi(csrf, accountId, features),
    [csrf, accountId, features],
  );
  const request = useMemo(() => workspaceApi(csrf), [csrf]);
  const [orders, setOrders] = useState<Order[]>([]),
    [id, setId] = useState(""),
    [order, setOrder] = useState<LoopOrder | null>(null),
    [changes, setChanges] = useState<Change[]>([]),
    [messages, setMessages] = useState<Message[]>([]),
    [context, setContext] = useState(0);
  const [summary, setSummary] = useState<Loop["DailySummary"] | null>(null),
    [settings, setSettings] = useState<Loop["ScheduleSettings"] | null>(null),
    [checklist, setChecklist] = useState<Loop["DeliveryChecklist"] | null>(
      null,
    ),
    [schedule, setSchedule] = useState<Loop["ScheduleCheck"] | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  const [detailReady, setDetailReady] = useState(false),
    [checkedAt, setCheckedAt] = useState(0),
    [settingsAt, setSettingsAt] = useState(0);
  const [source, setSource] = useState(""),
    [deferField, setDeferField] = useState<"schedule" | "address">("address"),
    [until, setUntil] = useState("");
  const [kind, setKind] = useState<"material" | "commitment" | "question">(
      "material",
    ),
    [owner, setOwner] = useState<"merchant" | "customer">("customer"),
    [text, setText] = useState(""),
    [due, setDue] = useState(""),
    [reason, setReason] = useState("");
  const report = useCallback(
    (e: unknown) => {
      setError(e instanceof Error ? e.message : "操作无法核对");
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        onSessionExpired();
    },
    [onSessionExpired],
  );
  const done = () => {
    setNotice("保存结果已确认，正在读取当前状态。");
    setRevision((v) => v + 1);
  };
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError("");
    void Promise.all([
      allPages<Order>(request, "/work-orders", abort.signal),
      api.read<Loop["DailySummary"]>("/daily-summary", abort.signal),
      api.read<Loop["ScheduleSettings"]>("/settings/schedule", abort.signal),
    ])
      .then(([list, s, c]) => {
        if (abort.signal.aborted) return;
        setOrders(list);
        setSummary(s);
        setSettings(c);
        setSettingsAt(Date.now());
        if (!id && list[0]) setId(list[0].id);
      })
      .catch((e) => {
        if (!abort.signal.aborted) report(e);
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [request, api, revision, report]);
  useEffect(() => {
    const abort = new AbortController();
    setDetailReady(false);
    setOrder(null);
    setChecklist(null);
    setSchedule(null);
    setSource("");
    if (id)
      void (async () => {
        const [o, c, s, ch] = await Promise.all([
          api.read<LoopOrder>(`/work-orders/${id}`, abort.signal),
          api.read<Loop["DeliveryChecklist"]>(
            `/work-orders/${id}/checklist`,
            abort.signal,
          ),
          api.read<Loop["ScheduleCheck"]>(
            `/work-orders/${id}/schedule-check`,
            abort.signal,
          ),
          allPages<Change>(request, `/work-orders/${id}/changes`, abort.signal),
        ]);
        if (
          o.account_id !== accountId ||
          o.id !== id ||
          c.work_order_id !== id ||
          s.work_order_id !== id
        )
          throw Error("工单归属无法核对");
        const conversation = o.conversation_ids[0];
        const [ms, info] = await Promise.all([
          allPages<Message>(
            request,
            `/conversations/${conversation}/messages`,
            abort.signal,
          ),
          request<Detail<components["schemas"]["Conversation"]>>(
            `/conversations/${conversation}`,
            undefined,
            abort.signal,
          ),
        ]);
        if (abort.signal.aborted) return;
        setOrder(o);
        setChecklist(c);
        setSchedule(s);
        setChanges(ch);
        setMessages(ms);
        setContext(info.data.context_version);
        setDetailReady(true);
        setCheckedAt(Date.now());
      })().catch((e) => {
        if (!abort.signal.aborted) report(e);
      });
    return () => abort.abort();
  }, [id, revision, api, request, accountId, report]);
  const sources = messages.filter(
    (m) =>
      m.direction === "incoming" &&
      !m.revoked &&
      !messages.some((n) => n.id === m.id && n.revision > m.revision),
  );
  const selectedSource = sources.find(
    (m) => m.id + ":" + m.revision === source,
  );
  const refs = selectedSource
    ? [
        {
          message_id: selectedSource.id,
          message_revision: selectedSource.revision,
        },
      ]
    : [];
  const common = {
    api,
    expiresAt: checkedAt + 10000,
    disabled: !detailReady,
    onDone: done,
    onError: report,
    onBusy: onBusyChange,
  };
  return (
    <section aria-label="业务管理">
      <div className="page-heading">
        <div>
          <p className="eyebrow">掌握每一步</p>
          <h1>业务管理</h1>
          <p>今日事项、工作时间、客户需求和交付核对。</p>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => setRevision((v) => v + 1)}
        >
          刷新业务管理
        </button>
      </div>
      {error && (
        <p role="alert" className="notice stale">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {summary && (
        <section className="panel">
          <h2>今日概览</h2>
          <small>
            {summary.date} · {summary.timezone}
          </small>
          <div className="summary-grid">
            {(
              [
                ["today", "今天要做"],
                ["waiting_for_customer", "等待客户"],
                ["due_soon", "即将到期"],
                ["needs_decision", "需要决定"],
              ] as const
            ).map(([key, label]) => (
              <div key={key}>
                <h3>{label}</h3>
                {summary[key].map((entry, index) => (
                  <p key={index}>
                    {entry.at && instant(entry.at)} {entry.title}{" "}
                    {entry.work_order_id && (
                      <button
                        className="text-button"
                        onClick={() => onOpenOrder(entry.work_order_id!)}
                      >
                        查看工单
                      </button>
                    )}
                  </p>
                ))}
                {!summary[key].length && <p className="subtle">暂无事项</p>}
              </div>
            ))}
          </div>
          {summary.suggestions.map((s, i) => (
            <p className="notice" key={i}>
              {s.detail}
            </p>
          ))}
        </section>
      )}
      <BusinessLoopReview
        api={api}
        csrf={csrf}
        accountId={accountId}
        features={features}
        orders={orders}
        onDone={done}
        onError={report}
        onBusy={onBusyChange}
      />
      {settings && (
        <details className="panel">
          <summary>工作时间与排期设置</summary>
          <div className="form-grid">
            <label>
              时区
              <input
                value={settings.timezone}
                onChange={(e) =>
                  setSettings({ ...settings, timezone: e.target.value })
                }
              />
            </label>
            <label>
              开始时间
              <input
                type="time"
                value={settings.work_hours.start}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    work_hours: {
                      ...settings.work_hours,
                      start: e.target.value,
                    },
                  })
                }
              />
            </label>
            <label>
              结束时间
              <input
                type="time"
                value={settings.work_hours.end}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    work_hours: { ...settings.work_hours, end: e.target.value },
                  })
                }
              />
            </label>
            {(
              [
                ["default_duration_minutes", "默认预约分钟"],
                ["buffer_minutes", "预约间隔分钟"],
                ["preparation_minutes", "准备提前分钟"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min="0"
                  value={settings[key]}
                  onChange={(e) =>
                    setSettings({ ...settings, [key]: Number(e.target.value) })
                  }
                />
              </label>
            ))}
          </div>
          <fieldset>
            <legend>工作日</legend>
            {["一", "二", "三", "四", "五", "六", "日"].map((d, i) => (
              <label className="inline-check" key={d}>
                <input
                  type="checkbox"
                  checked={settings.work_days.includes(i + 1)}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      work_days: e.target.checked
                        ? [...settings.work_days, i + 1].sort()
                        : settings.work_days.filter((n) => n !== i + 1),
                    })
                  }
                />
                周{d}
              </label>
            ))}
          </fieldset>
          <h3>休息时段</h3>
          {settings.breaks.map((b, i) => (
            <div className="row" key={i}>
              <input
                aria-label={`休息开始 ${i + 1}`}
                type="time"
                value={b.start}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    breaks: settings.breaks.map((x, j) =>
                      j === i ? { ...x, start: e.target.value } : x,
                    ),
                  })
                }
              />
              <input
                aria-label={`休息结束 ${i + 1}`}
                type="time"
                value={b.end}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    breaks: settings.breaks.map((x, j) =>
                      j === i ? { ...x, end: e.target.value } : x,
                    ),
                  })
                }
              />
              <button
                className="secondary"
                onClick={() =>
                  setSettings({
                    ...settings,
                    breaks: settings.breaks.filter((_, j) => j !== i),
                  })
                }
              >
                移除
              </button>
            </div>
          ))}
          <button
            className="secondary"
            onClick={() =>
              setSettings({
                ...settings,
                breaks: [...settings.breaks, { start: "12:00", end: "13:00" }],
              })
            }
          >
            添加休息时段
          </button>
          <LoopCommand
            {...common}
            disabled={!settingsAt}
            expiresAt={settingsAt + 10000}
            label="核对排期设置"
            intent={{
              path: "/settings/schedule",
              method: "PUT",
              body: {
                expected_version: settings.version,
                settings,
              } satisfies Loop["UpdateScheduleSettingsCommand"],
              review: `更新排期 v${settings.version}：${settings.timezone}，周${settings.work_days.join("、")}，${settings.work_hours.start}–${settings.work_hours.end}，休息 ${settings.breaks.map((b) => b.start + "–" + b.end).join("、") || "无"}；预约 ${settings.default_duration_minutes} 分钟、间隔 ${settings.buffer_minutes} 分钟、提前准备 ${settings.preparation_minutes} 分钟。`,
            }}
          />
        </details>
      )}
      <section className="panel">
        <h2>工单需求与交付</h2>
        <label>
          选择工单
          <select value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">请选择</option>
            {orders.map((o) => (
              <option key={o.id} value={o.id}>
                {o.summary}
              </option>
            ))}
          </select>
        </label>
        {order && (
          <>
            <h3>
              {order.summary}{" "}
              <span className="tag">
                {orderStates[order.status]} · v{order.version}
              </span>
            </h3>
            {schedule && (
              <div>
                <h3>排期核对</h3>
                {schedule.risks.map((r, i) => (
                  <p className="notice stale" key={i}>
                    {r.detail}
                  </p>
                ))}
                {!schedule.risks.length && <p>当前没有检测到排期风险。</p>}
                {schedule.suggestions.map((s, i) => (
                  <p key={i}>
                    {s.label} <small>候选时间，仍须与客户核实</small>
                  </p>
                ))}
              </div>
            )}
            {checklist && (
              <div>
                <h3>交付检查</h3>
                {checklist.items.map((c, i) => (
                  <p key={i}>
                    <span
                      className={`tag ${c.kind === "unfinished" ? "warning" : ""}`}
                    >
                      {c.kind === "unfinished" ? "待完成" : "已核对"}
                    </span>{" "}
                    {c.title}
                  </p>
                ))}
                <p>
                  {checklist.ready
                    ? "目前检查项齐全。"
                    : "请先处理未完成事项；确需结束时必须明确确认。"}
                </p>
              </div>
            )}
            {!["completed", "cancelled"].includes(order.status) && (
              <>
                <fieldset>
                  <legend>本次客户原文依据（主会话）</legend>
                  <select
                    aria-label="业务操作原文"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                  >
                    <option value="">先选择当前客户消息</option>
                    {sources.map((m) => (
                      <option
                        key={m.id + ":" + m.revision}
                        value={m.id + ":" + m.revision}
                      >
                        {m.text?.slice(0, 100) || "无文字"} · r{m.revision}
                      </option>
                    ))}
                  </select>
                  {selectedSource && (
                    <p className="message">{selectedSource.text}</p>
                  )}
                </fieldset>
                <details>
                  <summary>客户稍后确认</summary>
                  <label>
                    待确认项目
                    <select
                      value={deferField}
                      onChange={(e) =>
                        setDeferField(e.target.value as "schedule" | "address")
                      }
                    >
                      <option value="address">地址</option>
                      <option value="schedule">时间</option>
                    </select>
                  </label>
                  <label>
                    跟进时间（香港时间；留空则按后端默认）
                    <input
                      type="datetime-local"
                      value={until}
                      onChange={(e) => setUntil(e.target.value)}
                    />
                  </label>
                  {refs.length > 0 && (
                    <LoopCommand
                      {...common}
                      label="核对延期跟进"
                      intent={{
                        path: `/work-orders/${id}/defer`,
                        body: {
                          field: deferField,
                          expected_version: order.version,
                          sources: refs,
                          ...(until
                            ? {
                                until: new Date(
                                  until + ":00+08:00",
                                ).toISOString(),
                              }
                            : {}),
                        } satisfies Loop["DeferItemCommand"],
                        review: `工单 v${order.version}：客户稍后确认${deferField === "address" ? "地址" : "时间"}，${until || "使用后端默认日期"} 跟进；依据“${selectedSource?.text}”。保留缺项，暂停对此项的追问。`,
                      }}
                    />
                  )}
                </details>
                <details>
                  <summary>添加资料、承诺或问题</summary>
                  <div className="form-grid">
                    <label>
                      类型
                      <select
                        value={kind}
                        onChange={(e) => setKind(e.target.value as typeof kind)}
                      >
                        <option value="material">所需资料</option>
                        <option value="commitment">双方承诺</option>
                        <option value="question">未决问题</option>
                      </select>
                    </label>
                    <label>
                      由谁完成
                      <select
                        value={owner}
                        onChange={(e) =>
                          setOwner(e.target.value as typeof owner)
                        }
                      >
                        <option value="customer">客户</option>
                        <option value="merchant">商户</option>
                      </select>
                    </label>
                    <label>
                      内容
                      <textarea
                        value={text}
                        maxLength={300}
                        onChange={(e) => setText(e.target.value)}
                      />
                    </label>
                    <label>
                      期限（可留空）
                      <input
                        type="date"
                        value={due}
                        onChange={(e) => setDue(e.target.value)}
                      />
                    </label>
                  </div>
                  {refs.length > 0 && text.trim() && (
                    <LoopCommand
                      {...common}
                      label="核对新增条目"
                      intent={{
                        path: `/work-orders/${id}/requirements`,
                        body: {
                          kind,
                          owner,
                          text: text.trim(),
                          expected_version: order.version,
                          sources: refs,
                          due: due
                            ? {
                                kind: "date_only",
                                date: due,
                                timezone: "Asia/Hong_Kong",
                              }
                            : null,
                        } satisfies Loop["AddRequirementCommand"],
                        review: `工单 v${order.version}：${owner === "customer" ? "客户" : "商户"}负责“${text.trim()}”，期限 ${due || "未定"}。依据“${selectedSource?.text}”；资料与承诺将按规则生成待办。`,
                      }}
                    />
                  )}
                </details>
                {order.requirements?.map((r) => (
                  <article className="review-item" key={r.id}>
                    <h4>{r.text}</h4>
                    <p>
                      {r.owner === "customer" ? "客户" : "商户"} ·{" "}
                      {r.status === "open"
                        ? "未完成"
                        : r.status === "done"
                          ? "已完成"
                          : "已取消"}
                    </p>
                    {r.status === "open" &&
                      (["done", "cancelled"] as const).map((status) => (
                        <LoopCommand
                          {...common}
                          key={status}
                          label={
                            status === "done" ? "标记已完成" : "取消此条目"
                          }
                          intent={{
                            path: `/work-orders/${id}/requirements/${r.id}`,
                            body: { status, expected_version: order.version },
                            review: `工单 v${order.version}：将“${r.text}”标记为${status === "done" ? "已完成" : "取消"}，关联待办同步收尾。`,
                          }}
                        />
                      ))}
                  </article>
                ))}
                <label>
                  拒绝提议的原因
                  <input
                    value={reason}
                    maxLength={500}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                {changes
                  .filter(
                    (c) =>
                      c.status === "proposed" || c.status === "needs_review",
                  )
                  .map((c) => (
                    <article className="review-item" key={c.id}>
                      <h4>{fieldNames[c.field] || c.field}提议</h4>
                      <p>{fieldValue(c.new_value)}</p>
                      <p>
                        客户
                        {c.customer_confirmation === "confirmed"
                          ? "已确认"
                          : "仍待核实"}{" "}
                        · 工单 v{c.base_work_order_version}
                      </p>
                      {c.status === "proposed" &&
                        c.base_work_order_version === order.version &&
                        c.context_version === context &&
                        !c.conflict_ids.length &&
                        c.sources.every((r) =>
                          messages.some(
                            (m) =>
                              m.id === r.message_id &&
                              m.revision === r.message_revision &&
                              !m.revoked,
                          ),
                        ) && (
                          <LoopCommand
                            {...common}
                            label="接受此提议"
                            intent={{
                              path: `/work-orders/${id}/changes/${c.id}/confirm`,
                              body: {
                                expected_version: order.version,
                                expected_context_version: context,
                                apply_calendar_update: c.field === "schedule",
                              },
                              review: `工单 v${order.version}／会话 v${context}：接受${fieldNames[c.field]}“${fieldValue(c.new_value)}”。客户未确认的值仍保持待核实。`,
                            }}
                          />
                        )}
                      {reason.trim() && (
                        <LoopCommand
                          {...common}
                          label="拒绝此提议"
                          intent={{
                            path: `/work-orders/${id}/changes/${c.id}/reject`,
                            body: {
                              expected_version: order.version,
                              reason: reason.trim(),
                            },
                            review: `工单 v${order.version}：拒绝${fieldNames[c.field]}提议，原因“${reason.trim()}”。保留原安排及历史。`,
                          }}
                        />
                      )}
                    </article>
                  ))}
                {["confirmed", "in_progress", "waiting_customer"].includes(
                  order.status,
                ) && (
                  <LoopCommand
                    {...common}
                    label="检查后结束工单"
                    intent={{
                      path: `/work-orders/${id}/status`,
                      body: {
                        status: "completed",
                        expected_version: order.version,
                        acknowledge_open_items: !checklist?.ready,
                      },
                      review: `完成“${order.summary}” v${order.version}。${
                        checklist?.ready
                          ? "检查项已齐全。"
                          : "仍未完成：" +
                            checklist?.items
                              .filter((i) => i.kind === "unfinished")
                              .map((i) => i.title)
                              .join("；") +
                            "。确认仍要结束。"
                      } 自动待办收尾、释放时段，保留历史。`,
                    }}
                  />
                )}
              </>
            )}
            {["completed", "cancelled"].includes(order.status) &&
              !order.archived_at && (
                <LoopCommand
                  {...common}
                  label="归档此工单"
                  intent={{
                    path: `/work-orders/${id}/archive`,
                    body: { expected_version: order.version },
                    review: `归档已结束的“${order.summary}” v${order.version}，保留历史，不删除数据。`,
                  }}
                />
              )}
          </>
        )}
      </section>
    </section>
  );
}
