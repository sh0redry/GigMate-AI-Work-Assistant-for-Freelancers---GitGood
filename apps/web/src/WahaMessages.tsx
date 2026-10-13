import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  synchronizationApi,
  type SourceGap,
  type SyncJob,
  type TimelineMessage,
} from "./waha-sync-api";
import type { Choice, Issue } from "./connection-api";
import { WahaMedia } from "./WahaMedia";

const labels: Record<string, string> = {
  completed: "已处理",
  sent: "已发出",
  delivered: "已送达",
  read: "已读",
  unknown: "未知",
  pending: "排队中",
  running: "查询中",
  succeeded: "查询完成",
  failed: "失败",
  cancelled: "已取消",
  provider_exhausted: "已读完本次可获取记录",
  limit_reached: "已达查询上限",
  incomplete: "仍有未确认记录",
  in_progress: "进行中",
  needs_lookup: "待查询来源",
  snapshot_found: "找到快照，修订仍待核对",
  unavailable: "来源不可获取",
};

export function WahaMessages({
  connection,
  csrf,
  enabled,
  issues,
  onSessionExpired,
}: {
  connection: string;
  csrf: string;
  enabled: boolean;
  issues: Issue[];
  onSessionExpired?: () => void;
}) {
  const api = useMemo(
    () => synchronizationApi(connection, csrf),
    [connection, csrf],
  );
  const [chats, setChats] = useState<Choice[]>([]),
    [chat, setChat] = useState("");
  const [messages, setMessages] = useState<TimelineMessage[]>([]),
    [cursor, setCursor] = useState<string | null>(null);
  const [jobs, setJobs] = useState<SyncJob[]>([]),
    [gaps, setGaps] = useState<SourceGap[]>([]);
  const [days, setDays] = useState("7"),
    [maximum, setMaximum] = useState("500"),
    [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const active = useRef(true),
    epoch = useRef(0),
    attempt = useRef<{
      key: string;
      value: Parameters<typeof api.start>[0];
    } | null>(null);
  const report = useCallback(
    (e: unknown) => {
      setMessages([]);
      setCursor(null);
      const code = e instanceof Error ? e.message : "查询失败";
      setNotice(code);
      if (
        e &&
        typeof e === "object" &&
        "code" in e &&
        e.code === "UNAUTHENTICATED"
      )
        onSessionExpired?.();
    },
    [onSessionExpired],
  );
  const refresh = useCallback(async () => {
    const initial = epoch.current;
    try {
      const [choices, jobPage, gapPage] = await Promise.all([
        api.chats(),
        api.jobs(),
        api.gaps(),
      ]);
      if (!active.current || initial !== epoch.current) return;
      setChats(choices);
      setJobs(jobPage.items);
      setGaps(gapPage.items);
      if (chat && !choices.some((c) => c.id === chat)) {
        epoch.current++;
        setChat("");
        setMessages([]);
        setCursor(null);
        attempt.current = null;
        setConsent(false);
      }
    } catch (e) {
      if (active.current) report(e);
    }
  }, [api, chat, report]);
  useEffect(() => {
    active.current = true;
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => {
      active.current = false;
      clearInterval(timer);
    };
  }, [refresh]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setNotice("");
    try {
      await fn();
    } catch (e) {
      report(e);
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function load(more = false) {
    const initial = epoch.current;
    const page = await api.timeline(chat, more ? cursor : null);
    if (!active.current || initial !== epoch.current) return;
    setMessages((old) =>
      more
        ? [...old, ...page.items.filter((m) => !old.some((x) => x.id === m.id))]
        : page.items,
    );
    setCursor(page.next_cursor);
  }
  async function start(issue?: Issue, gap?: SourceGap, retry?: SyncJob) {
    if (!attempt.current) {
      const until = new Date(),
        since = new Date(until.getTime() - Number(days) * 86400000);
      attempt.current = {
        key: crypto.randomUUID(),
        value: {
          chat_ids: retry?.chat_ids ?? [gap?.chat_id ?? chat],
          since: retry?.since ?? issue?.started_at ?? since.toISOString(),
          until: retry?.until ?? issue?.recovered_at ?? until.toISOString(),
          max_records: retry?.max_records ?? Number(maximum),
          consent: true,
          issue_id: retry?.issue_id ?? issue?.id ?? null,
          source_gap_id: retry?.source_gap_id ?? gap?.id ?? null,
        },
      };
    }
    await api.start(attempt.current.value, attempt.current.key);
    attempt.current = null;
    setConsent(false);
    setNotice("同步已排队。历史快照不会自动创建工单或发送消息。");
    await refresh();
  }
  const waiting = jobs.some((j) => ["pending", "running"].includes(j.state));
  return (
    <section
      className="panel synchronization-panel"
      aria-label="消息时间线与同步"
    >
      <h2>消息时间线与同步</h2>
      <p>
        查看已授权聊天的消息，或明确导入近期可获取记录。图片、语音、文件仅记录类型与说明文字，原文件读取后续商议。
      </p>
      {notice && <p role="status">{notice}</p>}
      <label>
        已授权聊天
        <select
          value={chat}
          onChange={(e) => {
            epoch.current++;
            setChat(e.target.value);
            setMessages([]);
            setCursor(null);
            setConsent(false);
            attempt.current = null;
          }}
        >
          <option value="">请选择</option>
          {chats.map((c) => (
            <option key={c.id} value={c.id}>
              {c.kind === "group" ? "群聊 · " : ""}
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <div className="connection-actions">
        <button
          disabled={!chat || busy}
          onClick={() => void action(() => load())}
        >
          载入消息时间线
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void refresh()}
        >
          刷新同步状态
        </button>
      </div>
      {messages.length > 0 && (
        <ol className="message-timeline">
          {messages.map((m) => (
            <li key={m.id}>
              <small>
                {new Date(m.occurred_at).toLocaleString()} ·{" "}
                {m.origin === "history" ? "历史快照" : "实时接入"} ·{" "}
                {m.evidence === "revision"
                  ? `修订 ${m.revision}`
                  : "非完整修订证据"}{" "}
                · {m.direction === "incoming" ? "收到" : "自己发送"}
              </small>
              <p>{m.revoked ? "此消息已撤回" : (m.text ?? "无文字内容")}</p>
              {m.kind !== "text" && (
                <p>
                  {m.kind} · {m.filename ?? m.mimetype ?? "类型待确认"} ·
                  原文件通过下方授权入口读取
                </p>
              )}
              {m.kind !== "text" && !m.revoked && (
                <WahaMedia
                  key={`${m.id}:${m.occurred_at}`}
                  connection={connection}
                  csrf={csrf}
                  snapshot={m.id}
                  mimetype={
                    m.mimetype?.split(";")[0].trim().toLowerCase() ?? null
                  }
                  enabled={enabled}
                  onSessionExpired={onSessionExpired}
                />
              )}
              {m.sender_id && (
                <small>群成员标识：{m.sender_id.slice(-8)}</small>
              )}
              {m.reply_to_id && (
                <small> · 引用已接入消息 {m.reply_to_id.slice(-8)}</small>
              )}
              {m.processing_state && (
                <small>
                  {" "}
                  · 处理状态：{labels[m.processing_state] ?? m.processing_state}
                </small>
              )}
              {m.delivery_status && (
                <small>
                  {" "}
                  · 送达状态：{labels[m.delivery_status] ?? m.delivery_status}
                </small>
              )}
            </li>
          ))}
        </ol>
      )}
      {cursor && (
        <button disabled={busy} onClick={() => void action(() => load(true))}>
          加载更早消息
        </button>
      )}
      <fieldset disabled={busy || !enabled || !chat || waiting}>
        <legend>近期历史导入</legend>
        <label>
          时间范围
          <select
            value={days}
            onChange={(e) => {
              setDays(e.target.value);
              attempt.current = null;
            }}
          >
            {[1, 3, 7, 14].map((d) => (
              <option key={d} value={d}>
                近 {d} 天
              </option>
            ))}
          </select>
        </label>
        <label>
          查询记录上限
          <select
            value={maximum}
            onChange={(e) => {
              setMaximum(e.target.value);
              attempt.current = null;
            }}
          >
            {[100, 500, 1000].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          我同意查询所选聊天在该范围内的记录
        </label>
        <button disabled={!consent} onClick={() => void action(() => start())}>
          {attempt.current ? "重试原同步请求" : "开始历史同步"}
        </button>
      </fieldset>
      {!enabled && <p>接收已暂停，同步也已暂停；已有消息仍可查看。</p>}
      <p className="subtle">
        只同步 WAHA
        当前可提供的记录，不保证完整历史。已记录的暂停/撤权时段会跳过，失败和缺口不会自动清除。
      </p>
      <h3>同步任务</h3>
      {jobs.length === 0 ? (
        <p>暂无任务</p>
      ) : (
        <ul>
          {jobs.map((j) => (
            <li key={j.id}>
              {labels[j.state]} · 写入 {j.imported} · 已有 {j.duplicates} · 跳过{" "}
              {j.skipped} · {labels[j.coverage]}
              {j.error_code && ` · ${j.error_code}`}
              {j.state === "failed" &&
                j.chat_ids.length === 1 &&
                j.chat_ids[0] === chat && (
                  <button
                    disabled={
                      busy ||
                      !consent ||
                      !enabled ||
                      waiting ||
                      !!attempt.current
                    }
                    onClick={() =>
                      void action(() => start(undefined, undefined, j))
                    }
                  >
                    重试此范围
                  </button>
                )}
              {["pending", "running"].includes(j.state) && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      await api.cancel(j.id);
                      await refresh();
                    })
                  }
                >
                  取消同步
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {chat && consent && enabled && !waiting && (
        <>
          <h3>缺口补查</h3>
          <p>补查仅增加可获取快照，结果仍需本人核对。</p>
          {issues
            .filter(
              (i) =>
                i.recovered_at &&
                Date.parse(i.recovered_at) > Date.parse(i.started_at) &&
                (!i.acknowledged_at || i.resolution === "needs_followup") &&
                Date.now() - Date.parse(i.started_at) < 29 * 86400000,
            )
            .map((i) => (
              <button
                key={i.id}
                disabled={busy}
                onClick={() => void action(() => start(i))}
              >
                补查 {new Date(i.started_at).toLocaleString()} 的故障时段
              </button>
            ))}
        </>
      )}
      {gaps.length > 0 && (
        <>
          <h3>缺失来源</h3>
          <ul>
            {gaps
              .filter((g) => g.chat_id === chat)
              .map((g) => (
                <li key={g.id}>
                  {labels[g.state]} · {new Date(g.observed_at).toLocaleString()}
                  <button
                    disabled={busy || !enabled || !consent || waiting}
                    onClick={() => void action(() => start(undefined, g))}
                  >
                    查询来源快照，不重建修订
                  </button>
                </li>
              ))}
          </ul>
        </>
      )}
    </section>
  );
}
