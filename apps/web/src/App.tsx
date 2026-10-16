import { useCallback, useEffect, useState } from "react";
import { BusinessLoopWorkspace } from "./BusinessLoopWorkspace";
import { ConnectionWorkspace } from "./ConnectionWorkspace";
import { ApprovalsWorkspace } from "./ApprovalsWorkspace";
import { WorkOrderWorkspace } from "./WorkOrderWorkspace";
import { CalendarWorkspace } from "./CalendarWorkspace";
import { OrderCreation } from "./OrderCreation";
import { ReviewWorkspace } from "./ReviewWorkspace";
import { DeliveryGuide } from "./DeliveryGuide";
import { workspaceApi, type Detail, type Login } from "./workspace-api";
import { clearConnectionAttempts } from "./connection-api";
import { unavailableFeatures, loopReady, type Features } from "./features";
const pages = {
  business: "业务工作台",
  create: "新建工单",
  approvals: "回复审批",
  planning: "日历与待办",
  review: "人工复核",
  connect: "WhatsApp 连接",
  guide: "功能与使用说明",
  management: "业务管理",
};
type View = keyof typeof pages;
export function App() {
  const [view, setView] = useState<View>("business"),
    [selectedOrder, setSelectedOrder] = useState(""),
    [login, setLogin] = useState<Login | null>(null),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [features, setFeatures] = useState<Features>(unavailableFeatures),
    [featureError, setFeatureError] = useState("");
  const clearSession = useCallback((message: string) => {
    clearConnectionAttempts();
    setLogin(null);
    setPassword("");
    setUsername("");
    setView("business");
    setSelectedOrder("");
    setBusy(false);
    setFeatures(unavailableFeatures);
    setNotice(message);
  }, []);
  const expireSession = useCallback(
    () => clearSession("登录已过期，请重新登录。"),
    [clearSession],
  );
  useEffect(() => {
    if (!login) return;
    const abort = new AbortController();
    setFeatures(unavailableFeatures);
    setFeatureError("");
    void workspaceApi()<Detail<Features>>(
      "/workspace-capabilities",
      undefined,
      abort.signal,
    )
      .then((result) => {
        if (abort.signal.aborted) return;
        if (
          !result.data ||
          Object.keys(unavailableFeatures)
            .filter((key) => key !== "business_loop_reviewed")
            .some(
              (key) => typeof result.data[key as keyof Features] !== "boolean",
            )
        )
          throw new Error("后端能力状态不完整，请联系维护者更新服务。");
        setFeatures({
          ...result.data,
          business_loop_reviewed: result.data.business_loop_reviewed === true,
        });
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setFeatures(unavailableFeatures);
          setFeatureError(e instanceof Error ? e.message : "无法读取功能状态");
          if (e?.code === "UNAUTHENTICATED") expireSession();
        }
      });
    return () => abort.abort();
  }, [login, expireSession]);
  function navigate(next: View) {
    if (busy) return;
    setNotice("");
    setView(next);
    queueMicrotask(() => document.getElementById("workspace-content")?.focus());
  }
  const openOrder = useCallback((id: string) => {
    setSelectedOrder(id);
    setView("business");
    queueMicrotask(() => document.getElementById("workspace-content")?.focus());
  }, []);
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
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "登录失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    if (busy) return;
    setBusy(true);
    try {
      await workspaceApi(login?.csrf_token)("/auth/logout", {});
      clearSession("已退出。");
    } catch (e) {
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        clearSession("已退出，请重新登录。");
      else setNotice(e instanceof Error ? e.message : "暂时无法退出，请重试。");
    } finally {
      setBusy(false);
    }
  }
  const props = {
    csrf: login?.csrf_token ?? "",
    onSessionExpired: expireSession,
  };
  if (window.location.pathname.startsWith("/environments/"))
    return (
      <main className="panel login">
        <h1>旧入口已停用</h1>
        <p>
          本版只连接维护者配置的业务服务。为避免旧地址意外切换数据，请确认服务地址后再打开工作台。旧操作记录不会自动搬运。
        </p>
        <a href="/">打开当前工作台</a>
      </main>
    );
  return (
    <div className="shell">
      <a className="skip-link" href="#workspace-content">
        跳到主要内容
      </a>
      <header className="app-header">
        <a className="brand" href="#workspace-content">
          跟單 <span>GigMate</span>
        </a>
        <span className="mode">{login ? pages[view] : "把业务安排清楚"}</span>
        {login && (
          <div className="account-actions">
            <span>{login.username}</span>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void signOut()}
            >
              退出
            </button>
          </div>
        )}
      </header>
      {notice && (
        <div className="notice" role="status" aria-live="polite">
          {notice}
        </div>
      )}
      {!login ? (
        <main id="workspace-content" tabIndex={-1} className="welcome-grid">
          <section className="welcome-copy">
            <p className="eyebrow">为独立工作者整理每一次约定</p>
            <h1>
              从聊天里的约定，
              <br />
              到日历上的安排。
            </h1>
            <p>核对客户原文、管理工单和回复审批，让下一步清楚可见。</p>
            <p className="subtle">
              登录后可查看功能状态；未接通的能力会明确标注。
            </p>
          </section>
          <form
            className="panel login"
            onSubmit={(e) => {
              e.preventDefault();
              void signIn();
            }}
          >
            <h2>登录 GigMate</h2>
            <p>使用维护者为你配置的账号。</p>
            <label>
              账号
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                disabled={busy}
              />
            </label>
            <label>
              密码
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={busy}
              />
            </label>
            <button disabled={busy}>{busy ? "正在登录…" : "进入工作台"}</button>
            <small>
              这是 GigMate 的账号，不是 WhatsApp
              手机账号。没有账号或忘记密码时，请联系维护者。
            </small>
          </form>
        </main>
      ) : (
        <div className="app-layout">
          <nav className="workspace-navigation" aria-label="工作台页面">
            {Object.entries(pages)
              .filter(([id]) => id !== "management" || loopReady(features))
              .filter(([id]) => id !== "create" || features.create_order)
              .map(([id, label]) => (
                <button
                  key={id}
                  className="secondary"
                  aria-current={view === id ? "page" : undefined}
                  aria-pressed={view === id}
                  disabled={busy}
                  onClick={() => navigate(id as View)}
                >
                  {label}
                </button>
              ))}
          </nav>
          <main
            id="workspace-content"
            tabIndex={-1}
            className="workspace-content"
          >
            {featureError && (
              <p className="notice stale" role="status">
                暂时无法核对后端功能状态，依赖功能保持关闭。请在功能说明页查看详情。
              </p>
            )}
            {view === "business" && (
              <>
                <div className="page-heading">
                  <div>
                    <p className="eyebrow">业务工作台</p>
                    <h1>把变更核对清楚，再落实安排。</h1>
                    <p>
                      客户提出、客户确认和商户批准分别记录。正式更新需要你明确核对。
                    </p>
                  </div>
                  {features.create_order && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => navigate("create")}
                    >
                      新建工单
                    </button>
                  )}
                </div>
                <WorkOrderWorkspace
                  {...props}
                  key={login.account_id + selectedOrder}
                  accountId={login.account_id}
                  features={features}
                  initialSelected={selectedOrder}
                  onBusyChange={setBusy}
                />
              </>
            )}
            {view === "create" && (
              <OrderCreation
                {...props}
                accountId={login.account_id}
                features={features}
                onBusyChange={setBusy}
                onOpenOrder={openOrder}
              />
            )}
            {view === "approvals" && (
              <>
                <h1>回复审批</h1>
                <p className="availability-note">
                  批准只保存业务决定，尚未接通 WhatsApp
                  自动发送。手动发送请到连接页单独授权与核对；不会自动搬运已批准正文。
                </p>
                <ApprovalsWorkspace
                  {...props}
                  accountId={login.account_id}
                  onBusyChange={setBusy}
                />
              </>
            )}
            {view === "planning" && (
              <CalendarWorkspace
                {...props}
                features={features}
                onOpenOrder={openOrder}
              />
            )}
            {view === "review" && (
              <ReviewWorkspace
                {...props}
                onOpenOrder={openOrder}
                onConnect={() => navigate("connect")}
              />
            )}
            {view === "connect" && (
              <>
                <h1>WhatsApp 连接与消息</h1>
                <p className="availability-note">
                  手动发送网关已提供，需要单独发送授权。AI
                  润色、业务审批直发与自由生成自动回复尚未接通。
                </p>
                <ConnectionWorkspace {...props} onBusyChange={setBusy} />
              </>
            )}
            {view === "management" && (
              <BusinessLoopWorkspace
                {...props}
                accountId={login.account_id}
                features={features}
                onBusyChange={setBusy}
                onOpenOrder={openOrder}
              />
            )}
            {view === "guide" && (
              <DeliveryGuide features={features} error={featureError} />
            )}
          </main>
        </div>
      )}
      <footer>
        你的聊天由你授权；正式安排需要确认。批准、发送与客户确认是不同步骤。
      </footer>
    </div>
  );
}
