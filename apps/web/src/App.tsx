import { currentEnvironment, environmentConfig } from "./environment";
import { useCallback, useState } from "react";
import { ConnectionWorkspace } from "./ConnectionWorkspace";
import { WorkOrderWorkspace } from "./WorkOrderWorkspace";
import { workspaceApi, type Detail, type Login } from "./workspace-api";
import { clearConnectionAttempts } from "./connection-api";

export function App() {
  const environment = currentEnvironment();
  const config = environmentConfig();
  const canConnect = environment !== "isolated";
  const [view, setView] = useState<"connect" | "business">("business");
  const [login, setLogin] = useState<Login | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const activeView = canConnect ? view : "business";
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const csrf = login?.csrf_token ?? "";
  const clearSession = useCallback((message: string) => {
    clearConnectionAttempts();
    setLogin(null);
    setPassword("");
    setView("business");
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
            ? activeView === "connect"
              ? "WhatsApp 连接"
              : "业务工作台"
            : "欢迎使用"}
        </div>
      </header>
      {config && environment && (
        <section
          className={`environment-panel ${environment}`}
          aria-label="当前环境与切换"
        >
          <div className="row">
            <strong>
              当前：
              {config.syntheticProvider
                ? "合成连接自检（虚构数据）"
                : environment === "real"
                  ? "真实连接（本机开发）"
                  : "隔离测试（虚构数据）"}
            </strong>
            {!config.syntheticProvider && (
              <a
                className="environment-switch"
                href={`/environments/${environment === "real" ? "isolated" : "real"}/`}
                aria-disabled={busy}
                onClick={(event) => {
                  if (busy) event.preventDefault();
                }}
              >
                切换到{environment === "real" ? "隔离测试" : "真实连接"}
              </a>
            )}
          </div>
          <p>
            {config.syntheticProvider
              ? "这是自动自检工具的临时数据库和模拟 WhatsApp 服务，没有真实聊天；二维码是不可扫码的图片样例。这里只提供合成连接流程，不切换到你自己的后端。"
              : environment === "real"
                ? "连接你自己的 WAHA 和本机业务数据库，授权与操作会影响该环境的真实记录。仍是开发环境，尚未正式上线。"
                : "连接独立测试数据库，只含虚构工单，用来练习核对变更、日历和待办；不接收真实 WhatsApp 聊天。"}
          </p>
          <small>
            后端地址：{config.targets[environment]}
            {config.syntheticProvider
              ? "。自检结束后临时资源会被清理。"
              : "。切换后重新登录；两边的数据、登录凭据和待核对请求分别保留，不搬运数据。操作处理中暂不可切换。"}
          </small>
        </section>
      )}
      {login && (
        <nav className="workspace-navigation" aria-label="工作台页面">
          <button
            className="secondary"
            aria-pressed={activeView === "business"}
            disabled={busy}
            onClick={() => navigate("business")}
          >
            业务工作台
          </button>
          {canConnect && (
            <button
              className="secondary"
              aria-pressed={activeView === "connect"}
              disabled={busy}
              onClick={() => navigate("connect")}
            >
              WhatsApp 连接
            </button>
          )}
        </nav>
      )}
      {login && activeView === "business" && (
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
          <p>
            {canConnect
              ? "使用为你配置的 GigMate 账号登录，管理业务和 WhatsApp 会话授权。"
              : "使用测试账号登录，练习虚构工单、变更核对、日历和待办。"}
          </p>
          {config && (
            <div className="test-account">
              <strong>公开开发测试账号</strong>
              <p>
                账号：<code>{config.publicTestAccount.username}</code>
                <br />
                密码：<code>{config.publicTestAccount.password}</code>
              </p>
              <small>
                {config.syntheticProvider
                  ? "仅用于自动自检的临时数据库；不连接你的 WhatsApp 账号。"
                  : environment === "isolated"
                    ? "用于隔离测试数据库。若维护者改过密码，以实际配置为准。"
                    : "真实连接环境也可能使用此默认开发账号；如果你改过密码，请用自己的配置。它不是 WhatsApp 密码，也不是正式上线账号。"}
              </small>
            </div>
          )}
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
          {activeView === "connect" ? (
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
