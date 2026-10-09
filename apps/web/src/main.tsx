import { useCallback, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { ConnectionWorkspace } from "./ConnectionWorkspace";
import { ReplayWorkspace } from "./ReplayWorkspace";
import { workspaceApi, type Detail, type Login } from "./workspace-api";
import { clearConnectionAttempts } from "./connection-api";

function App() {
  const [view, setView] = useState<"connect" | "replay" | "demo">("connect");
  const [login, setLogin] = useState<Login | null>(null);
  const [username, setUsername] = useState("merchant");
  const [password, setPassword] = useState("demo-only-change-me");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const csrf = login?.csrf_token ?? "";
  const clearSession = useCallback((message: string) => {
    clearConnectionAttempts();
    setLogin(null);
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
      setNotice("已登录本地工作台");
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
          disabled={busy}
          onClick={() => navigate("connect")}
        >
          WhatsApp 连接
        </button>
        {login && (
          <button
            className="secondary"
            aria-pressed={view === "replay"}
            disabled={busy}
            onClick={() => navigate("replay")}
          >
            工单回放
          </button>
        )}
        <button
          className="secondary"
          aria-pressed={view === "demo"}
          disabled={busy}
          onClick={() => navigate("demo")}
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
      {notice && (
        <div className="notice" role="status" aria-live="polite">
          {notice}
        </div>
      )}
      {view === "demo" ? (
        <ConnectionWorkspace demo />
      ) : !login ? (
        <form
          className="panel login"
          onSubmit={(event) => {
            event.preventDefault();
            void signIn();
          }}
        >
          <h2>登录 GigMate 工作台</h2>
          <p>使用本机开发账号查看连接状态或回放样例。</p>
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
            <ReplayWorkspace
              csrf={csrf}
              username={login.username}
              onSessionExpired={expireSession}
              onBusyChange={setBusy}
            />
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
