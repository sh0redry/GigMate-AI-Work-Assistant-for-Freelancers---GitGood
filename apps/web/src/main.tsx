import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { components } from "./generated/api";
import "./style.css";
import { ConnectionWorkspace } from "./ConnectionWorkspace";

type Order = components["schemas"]["WorkOrder"];
type Change = components["schemas"]["ChangeView"];
type Message = components["schemas"]["ConversationMessage"];
type Task = components["schemas"]["Task"];
type Calendar = components["schemas"]["CalendarEvent"];
type Login = components["schemas"]["LoginResult"];
type Confirm = components["schemas"]["ConfirmChangeCommand"];
type Page<T> = { items: T[]; next_cursor: string | null; request_id: string };
type Detail<T> = { data: T; request_id: string };

async function api<T>(path: string, csrf: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      `${result.error?.code ?? response.status}：${result.error?.message ?? "请求失败"}`,
    );
  return result as T;
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
  if (!item.start_at || !item.end_at) return "待核对";
  const options: Intl.DateTimeFormatOptions = {
    timeZone: "Asia/Hong_Kong",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  };
  return `${new Date(item.start_at).toLocaleString("zh-CN", options)} → ${new Date(item.end_at).toLocaleString("zh-CN", options)}`;
}

function App() {
  const [view, setView] = useState<"connect" | "replay" | "demo">("connect");
  const [login, setLogin] = useState<Login | null>(null);
  const [username, setUsername] = useState("merchant");
  const [password, setPassword] = useState("demo-only-change-me");
  const [orders, setOrders] = useState<Order[]>([]);
  const [selected, setSelected] = useState("");
  const [changes, setChanges] = useState<Change[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [calendar, setCalendar] = useState<Calendar[]>([]);
  const [contextVersion, setContextVersion] = useState(0);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const csrf = login?.csrf_token ?? "";
  const order = orders.find((item) => item.id === selected);
  const expireSession = useCallback(() => {
    setLogin(null);
    setOrders([]);
    setSelected("");
    setChanges([]);
    setMessages([]);
    setTasks([]);
    setCalendar([]);
    setContextVersion(0);
    setNotice("登录已过期，请重新登录。");
  }, []);

  const refresh = useCallback(async () => {
    if (!login || view !== "replay") return;
    const [o, t, c] = await Promise.all([
      api<Page<Order>>("/work-orders", csrf),
      api<Page<Task>>("/tasks", csrf),
      api<Page<Calendar>>("/calendar-events", csrf),
    ]);
    setOrders(o.items);
    setTasks(t.items);
    setCalendar(c.items);
    const current = selected || o.items[0]?.id;
    if (!current) return;
    setSelected(current);
    const conversation = o.items.find((item) => item.id === current)
      ?.conversation_ids[0];
    const [ch, m, info] = await Promise.all([
      api<Page<Change>>(`/work-orders/${current}/changes`, csrf),
      api<Page<Message>>(`/conversations/${conversation}/messages`, csrf),
      api<Detail<{ context_version: number }>>(
        `/conversations/${conversation}`,
        csrf,
      ),
    ]);
    setChanges(ch.items);
    setMessages(
      m.items.sort((a, b) => a.occurred_at.localeCompare(b.occurred_at)),
    );
    setContextVersion(info.data.context_version);
  }, [login, csrf, selected, view]);

  useEffect(() => {
    if (!login || view !== "replay") return;
    const update = () => {
      void refresh().catch((error) => setNotice(String(error)));
    };
    update();
    const timer = setInterval(update, 1500);
    return () => clearInterval(timer);
  }, [login, refresh, view]);

  async function act(task: () => Promise<unknown>, success: string) {
    setBusy(true);
    setNotice("");
    try {
      await task();
      setNotice(success);
      await refresh();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header>
        <div className="brand">
          跟單 <span>GigMate</span>
        </div>
        <div className="mode">
          {view === "demo"
            ? "合成演示"
            : view === "connect"
              ? "本地连接工作台"
              : "虚构数据 · 回放模式"}
        </div>
      </header>
      <nav className="workspace-navigation" aria-label="工作台页面">
        <button
          className="secondary"
          aria-pressed={view === "connect"}
          onClick={() => setView("connect")}
        >
          WhatsApp 连接
        </button>
        {login && (
          <button
            className="secondary"
            aria-pressed={view === "replay"}
            onClick={() => setView("replay")}
          >
            工单回放
          </button>
        )}
        <button
          className="secondary"
          aria-pressed={view === "demo"}
          onClick={() => setView("demo")}
        >
          D-01 演示预览
        </button>
      </nav>
      {view === "replay" && (
        <section className="intro">
          <p className="eyebrow">业务协作工作台</p>
          <h1>把变更核对清楚，再落实安排。</h1>
          <p>
            查看原文、检查冲突、确认业务变化。这里使用固定抽取桩，没有连接真实
            WhatsApp，也不会发送消息。
          </p>
        </section>
      )}
      {(notice || view === "replay") && (
        <div className="notice" role="status" aria-live="polite">
          {notice || "所有时间以香港时区显示。顾客提议不会自动覆盖正式安排。"}
        </div>
      )}
      {view === "demo" ? (
        <ConnectionWorkspace demo />
      ) : !login ? (
        <form
          className="panel login"
          onSubmit={(event) => {
            event.preventDefault();
            void act(async () => {
              const result = await api<Detail<Login>>("/auth/login", "", {
                username,
                password,
              });
              setLogin(result.data);
            }, "已登录本地工作台");
          }}
        >
          <h2>登录 GigMate 工作台</h2>
          <p>先登录本地工作台，再连接你的 WhatsApp。预置账号仅供开发。</p>
          <label>
            账号
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button disabled={busy}>进入工作台</button>
          <small>
            默认开发密码为
            demo-only-change-me；如修改了环境配置，请输入设置后的值。
          </small>
        </form>
      ) : (
        <>
          <div className="toolbar">
            <span>当前账号：{login.username}</span>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await api("/auth/logout", csrf, {});
                  setLogin(null);
                  setOrders([]);
                  setSelected("");
                  setChanges([]);
                  setMessages([]);
                }, "已退出")
              }
            >
              退出
            </button>
          </div>
          {view === "connect" ? (
            <ConnectionWorkspace csrf={csrf} onSessionExpired={expireSession} />
          ) : (
            <div className="grid">
              <aside className="panel">
                <h2>业务列表</h2>
                {orders.map((item) => (
                  <button
                    key={item.id}
                    className={`order ${selected === item.id ? "active" : ""}`}
                    onClick={() => setSelected(item.id)}
                  >
                    <strong>{item.summary}</strong>
                    <small>
                      版本 {item.version} · {item.status}
                    </small>
                  </button>
                ))}
                <h3>回放输入</h3>
                <p>先看冲突，再回放可用时段。重复同一输入不会重复建单。</p>
                <button
                  className="secondary"
                  disabled={busy || login.username !== "merchant"}
                  onClick={() =>
                    void act(
                      () => api("/replay", csrf, { scenario: "reschedule" }),
                      "改期消息已进入持久队列，等待后台处理",
                    )
                  }
                >
                  回放：15:00 冲突改期
                </button>
                <button
                  disabled={busy || login.username !== "merchant"}
                  onClick={() =>
                    void act(
                      () => api("/replay", csrf, { scenario: "available" }),
                      "可用时段消息已进入持久队列",
                    )
                  }
                >
                  回放：16:30 可用时段
                </button>
              </aside>
              <main className="panel">
                <h2>待核对的业务变化</h2>
                {order && (
                  <div className="confirmed">
                    <small>
                      当前正式安排 · 业务版本 {order.version} · 会话版本{" "}
                      {contextVersion}
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
                {!changes.length && (
                  <p className="empty">
                    还没有变更提议。回放一条消息后，后台会生成带原文依据的提议。
                  </p>
                )}
                {changes.map((change) => (
                  <article className="change" key={change.id}>
                    <div className="row">
                      <h3>改期提议</h3>
                      <span
                        className={`tag ${change.conflict_ids.length ? "warning" : ""}`}
                      >
                        {change.status === "confirmed"
                          ? "已确认"
                          : change.status === "needs_review"
                            ? "已失效，需复核"
                            : change.conflict_ids.length
                              ? "时间冲突"
                              : "待商户确认"}
                      </span>
                    </div>
                    <p>原安排：{schedule(change.old_value)}</p>
                    <p>
                      <strong>新提议：{schedule(change.new_value)}</strong>
                    </p>
                    <small>
                      来源消息：
                      {change.sources
                        .map(
                          (source) =>
                            `${source.message_id.slice(-4)} · r${source.message_revision}`,
                        )
                        .join(", ")}
                    </small>
                    <p>
                      {change.conflict_ids.length
                        ? "该时段与另一项已确认预约重叠，不能确认。"
                        : "确认后将同步正式日历，取消旧自动待办并生成新的准备事项。"}
                    </p>
                    <button
                      disabled={
                        busy ||
                        change.status !== "proposed" ||
                        change.conflict_ids.length > 0
                      }
                      onClick={() => {
                        if (!order) return;
                        const command: Confirm = {
                          expected_version: order.version,
                          expected_context_version: contextVersion,
                          apply_calendar_update: true,
                        };
                        void act(
                          () =>
                            api(
                              `/work-orders/${order.id}/changes/${change.id}/confirm`,
                              csrf,
                              command,
                            ),
                          "已确认并持久化工单、日历和待办",
                        );
                      }}
                    >
                      确认并同步安排
                    </button>
                  </article>
                ))}
                <h2>来源时间线</h2>
                {messages.map((message) => (
                  <div className="message" key={message.id}>
                    <small>
                      {message.direction === "incoming" ? "顾客" : "商户"} ·{" "}
                      {message.source} · r{message.revision}
                    </small>
                    <p>
                      {message.revoked
                        ? "消息已撤回，相关内容需要复核"
                        : message.text}
                    </p>
                  </div>
                ))}
              </main>
              <aside className="panel">
                <h2>个人安排</h2>
                {calendar.map((event) => (
                  <div className="calendar" key={event.id}>
                    <span>
                      {event.work_order_id === selected
                        ? "当前业务"
                        : "其他业务"}
                    </span>
                    <strong>{schedule(event.schedule)}</strong>
                  </div>
                ))}
                <h2>待办事项</h2>
                {tasks
                  .filter((task) => task.work_order_id === selected)
                  .map((task) => (
                    <div className="task" key={task.id}>
                      <strong>{task.title}</strong>
                      <small>
                        {task.state} · 业务版本 {task.work_order_version}
                      </small>
                    </div>
                  ))}
              </aside>
            </div>
          )}
        </>
      )}
      <footer>
        工程骨架 v0.2 · 固定样例不是模型效果评测 · 实际外发尚未实现
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
