import { useCallback, useState } from "react";
import { ConnectionWorkspace } from "./ConnectionWorkspace";
import { WorkOrderWorkspace } from "./WorkOrderWorkspace";
import { workspaceApi, type Detail, type Login } from "./workspace-api";
import { clearConnectionAttempts } from "./connection-api";

export function App() {
  const [view, setView] = useState<"connect" | "business">("business");
  const [login, setLogin] = useState<Login | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const csrf = login?.csrf_token ?? "";
  const clearSession = useCallback((message: string) => {
    clearConnectionAttempts();
    setLogin(null);
    setPassword("");
    setView("connect");
    setBusy(false);
    setNotice(message);
  }, []);
  const expireSession = useCallback(
    () => clearSession("登录已过期，请重新登录。"),
    [clearSession],
  );
  function navigate(next: typeof view) {
    setNotice("");
    setView(next);
  }
  async function signIn() {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await workspaceApi()<Detail<Login>>("/auth/login", {
        username,
        password,
      });
      setLogin(result.data);
      setPassword("");
      setView("business");
      setNotice("已登录工作台");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "登录失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    if (busy) return;
    setBusy(true);
    try {
      await workspaceApi(csrf)("/auth/logout", {});
      clearSession("已退出。");
    } catch (error) {
      if ((error as { code?: string })?.code === "UNAUTHENTICATED")
        clearSession("已退出，请重新登录。");
      else
        setNotice(
          error instanceof Error ? error.message : "暂时无法退出，请重试。",
        );
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
          {login
            ? view === "connect"
              ? "WhatsApp 连接"
              : "业务工作台"
            : "欢迎使用"}
        </div>
      </header>
      {login && (
        <nav className="workspace-navigation" aria-label="工作台页面">
          <button
            className="secondary"
            aria-pressed={view === "business"}
            disabled={busy}
            onClick={() => navigate("business")}
          >
            业务工作台
          </button>
          <button
            className="secondary"
            aria-pressed={view === "connect"}
            disabled={busy}
            onClick={() => navigate("connect")}
          >
            WhatsApp 连接
          </button>
        </nav>
      )}
      {login && view === "business" && (
        <section className="intro">
          <p className="eyebrow">业务协作工作台</p>
          <h1>把变更核对清楚，再落实安排。</h1>
          <p>查看工单和原文、核对变更、同步日历与待办。此页面不会发送消息。</p>
        </section>
      )}
      {notice && (
        <div className="notice" role="status" aria-live="polite">
          {notice}
        </div>
      )}
      {!login ? (
        <form
          className="panel login"
          onSubmit={(event) => {
            event.preventDefault();
            void signIn();
          }}
        >
          <h2>登录 GigMate 工作台</h2>
          <p>使用为你配置的 GigMate 账号登录，管理业务和 WhatsApp 会话授权。</p>
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
            这是 GigMate 的账号，不是 WhatsApp
            手机账号。不清楚账号时，请联系负责配置的队友。
          </small>
        </form>
      ) : (
        <>
          <div className="toolbar">
            <span>当前账号：{login.username}</span>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void signOut()}
            >
              退出
            </button>
          </div>
          {view === "connect" ? (
            <ConnectionWorkspace
              csrf={csrf}
              onSessionExpired={expireSession}
              onBusyChange={setBusy}
            />
          ) : (
            <WorkOrderWorkspace
              key={view}
              csrf={csrf}
              onSessionExpired={expireSession}
              onBusyChange={setBusy}
            />
          )}
        </>
      )}
      <footer>
        你的聊天由你授权；正式安排需要确认。消息发送功能尚未开放。
      </footer>
    </div>
  );
}
