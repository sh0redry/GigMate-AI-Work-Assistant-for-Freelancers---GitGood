import { t, localized, useLocale, setLocale } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { useCallback, useEffect } from "react";
import { clearReadCache, setReadScope } from "./read-cache";
import { NavIcon } from "./NavIcon";
import { BusinessLoopWorkspace } from "./BusinessLoopWorkspace";
import { ConnectionWorkspace } from "./ConnectionWorkspace";
import { ApprovalsWorkspace } from "./ApprovalsWorkspace";
import { WorkOrderWorkspace } from "./WorkOrderWorkspace";
import { HomeWorkspace } from "./HomeWorkspace";
import { CalendarWorkspace } from "./CalendarWorkspace";
import { OrderCreation } from "./OrderCreation";
import { ReviewWorkspace } from "./ReviewWorkspace";
import { DeliveryGuide } from "./DeliveryGuide";
import { GuidedTour, tourSeen } from "./GuidedTour";
import { NewRequestBanner } from "./new-request-banner";
import { workspaceApi, type Detail, type Login } from "./workspace-api";
import { clearConnectionAttempts } from "./connection-api";
import { unavailableFeatures, loopReady, type Features } from "./features";
const pages = localized({
  home: "今日",
  business: "业务工作台",
  create: "新建工单",
  approvals: "回复审批",
  planning: "日历与待办",
  review: "人工复核",
  connect: "WhatsApp 连接",
  guide: "功能与使用说明",
  management: "业务管理",
});
type View = keyof typeof pages;
export function App() {
  const language = useLocale();
  useEffect(() => {
    document.documentElement.lang =
      language === "en"
        ? "en-HK"
        : language === "yue"
          ? "yue-Hant-HK"
          : "zh-CN";
  }, [language]);
  const [moreOpen, setMoreOpen] = useState(false),
    [tourOpen, setTourOpen] = useState(false);
  const [view, setView] = useState<View>("home"),
    [selectedOrder, setSelectedOrder] = useState(""),
    [createConversation, setCreateConversation] = useState(""),
    [createSuggestion, setCreateSuggestion] = useState(""),
    [sendAction, setSendAction] = useState(""),
    [login, setLogin] = useState<Login | null>(null),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [features, setFeatures] = useState<Features>(unavailableFeatures),
    [featureError, setFeatureError] = useState("");
  // First visit for this account on this browser: start the walkthrough.
  useEffect(() => {
    if (login && !tourSeen(login.account_id)) setTourOpen(true);
    if (!login) setTourOpen(false);
  }, [login]);
  const clearSession = useCallback((message: string) => {
    clearConnectionAttempts();
    setReadScope("");
    clearReadCache();
    setLogin(null);
    setPassword("");
    setUsername("");
    setView("home");
    setMoreOpen(false);
    setSelectedOrder("");
    setCreateConversation("");
    setBusy(false);
    setFeatures(unavailableFeatures);
    setNotice(message);
  }, []);
  const expireSession = useCallback(
    () => clearSession(t("登录已过期，请重新登录。")),
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
            .filter(
              (key) =>
                !["business_loop_reviewed", "manual_field_editing"].includes(
                  key,
                ),
            )
            .some(
              (key) => typeof result.data[key as keyof Features] !== "boolean",
            )
        )
          throw new Error(t("后端能力状态不完整，请联系维护者更新服务。"));
        setFeatures({
          ...result.data,
          business_loop_reviewed: result.data.business_loop_reviewed === true,
          manual_field_editing: result.data.manual_field_editing === true,
        });
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setFeatures(unavailableFeatures);
          setFeatureError(
            e instanceof Error ? e.message : t("无法读取功能状态"),
          );
          if (e?.code === "UNAUTHENTICATED") expireSession();
        }
      });
    return () => abort.abort();
  }, [login, expireSession]);
  function navigate(next: View) {
    if (busy) return;
    if (next === "create") {
      setCreateConversation("");
      setCreateSuggestion("");
    }
    if (next !== "management") setSendAction("");
    setNotice("");
    setView(next);
    setMoreOpen(false);
    queueMicrotask(() => {
      document
        .getElementById("workspace-content")
        ?.focus({ preventScroll: true });
      document.scrollingElement?.scrollTo({ top: 0 });
    });
  }
  const openOrder = useCallback((id: string) => {
    setSelectedOrder(id);
    setView("business");
    queueMicrotask(() => {
      document
        .getElementById("workspace-content")
        ?.focus({ preventScroll: true });
      document.scrollingElement?.scrollTo({ top: 0 });
    });
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
      setReadScope(result.data.account_id + ":" + result.data.csrf_token);
      setLogin(result.data);
      setPassword("");
      setView("home");
      setNotice("");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : t("登录失败，请重试。"));
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    if (busy) return;
    setBusy(true);
    try {
      await workspaceApi(login?.csrf_token)("/auth/logout", {});
      clearSession(t("已退出。"));
    } catch (e) {
      if ((e as { code?: string })?.code === "UNAUTHENTICATED")
        clearSession(t("已退出，请重新登录。"));
      else
        setNotice(e instanceof Error ? e.message : t("暂时无法退出，请重试。"));
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
        <h1>{t("旧入口已停用")}</h1>
        <p>
          {t(
            "本版只连接维护者配置的业务服务。为避免旧地址意外切换数据，请确认服务地址后再打开工作台。旧操作记录不会自动搬运。",
          )}
        </p>
        <a href="/">{t("打开当前工作台")}</a>
      </main>
    );
  return (
    <div className="shell">
      <a className="skip-link" href="#workspace-content">
        {t("跳到主要内容")}
      </a>
      <header className="app-header">
        <div
          className="language-switch"
          role="group"
          aria-label={t("界面语言")}
        >
          {(
            [
              ["zh", "中文"],
              ["en", "English"],
              ["yue", "粵語"],
            ] as const
          ).map(([id, label]) => (
            <button
              type="button"
              key={id}
              aria-pressed={language === id}
              onClick={() => setLocale(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <a className="brand" href="#workspace-content">
          {t("跟單")}
          <span>GigMate</span>
        </a>
        <span className="mode">
          {login ? pages[view] : t("把业务安排清楚")}
        </span>
        {login && (
          <div className="account-actions">
            <span>{login.username}</span>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void signOut()}
            >
              {t("退出")}
            </button>
          </div>
        )}
      </header>
      {notice && (
        <div className="notice" role="status" aria-live="polite">
          {t(notice)}
        </div>
      )}
      {!login ? (
        <main id="workspace-content" tabIndex={-1} className="welcome-grid">
          <section className="welcome-copy">
            <p className="eyebrow">{t("为独立工作者整理每一次约定")}</p>
            <h1>
              {t("从聊天里的约定，")}
              <br />
              {t("到日历上的安排。")}
            </h1>
            <p>{t("核对客户原文、管理工单和回复审批，让下一步清楚可见。")}</p>
            <p className="subtle">
              {t("登录后可查看功能状态；未接通的能力会明确标注。")}
            </p>
          </section>
          <form
            className="panel login"
            onSubmit={(e) => {
              e.preventDefault();
              void signIn();
            }}
          >
            <h2>{t("登录 GigMate")}</h2>
            <p>{t("使用维护者为你配置的账号。")}</p>
            <label>
              {t("账号")}
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                disabled={busy}
              />
            </label>
            <label>
              {t("密码")}
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={busy}
              />
            </label>
            <button disabled={busy}>
              {busy ? t("正在登录…") : t("进入工作台")}
            </button>
            <small>
              {t(
                "这是 GigMate 的账号，不是 WhatsApp 手机账号。没有账号或忘记密码时，请联系维护者。",
              )}
            </small>
          </form>
        </main>
      ) : (
        <div className="app-layout">
          <nav
            className="workspace-navigation"
            aria-label={t("工作台页面")}
            onKeyDown={(e) => {
              if (e.key === "Escape") setMoreOpen(false);
            }}
            data-expanded={moreOpen}
          >
            <p className="nav-caption">{t("我的工作空间")}</p>
            <div className="nav-primary">
              {(["home", "business", "approvals", "planning"] as View[]).map(
                (id) => (
                  <button
                    key={id}
                    className="secondary"
                    aria-current={view === id ? "page" : undefined}
                    aria-pressed={view === id}
                    data-tour={"nav-" + id}
                    disabled={busy}
                    onClick={() => navigate(id)}
                  >
                    <NavIcon name={id} />
                    <span>{pages[id]}</span>
                  </button>
                ),
              )}
            </div>
            <div className="nav-secondary" id="additional-pages">
              {(
                ["connect", "create", "review", "management", "guide"] as View[]
              )
                .filter((id) => id !== "management" || loopReady(features))
                .filter((id) => id !== "create" || features.create_order)
                .map((id) => (
                  <button
                    key={id}
                    className="secondary"
                    aria-current={view === id ? "page" : undefined}
                    aria-pressed={view === id}
                    data-tour={"nav-" + id}
                    disabled={busy}
                    onClick={() => navigate(id)}
                  >
                    <NavIcon name={id} />
                    <span>{pages[id]}</span>
                  </button>
                ))}
            </div>
            <button
              className="secondary mobile-more"
              aria-expanded={moreOpen}
              aria-controls="additional-pages"
              disabled={busy}
              onClick={() => setMoreOpen((v) => !v)}
            >
              <NavIcon name="more" />
              <span>{moreOpen ? t("收起") : t("更多")}</span>
            </button>
            <small className="nav-footnote">
              {t("每一份约定，清楚有序。")}
            </small>
          </nav>
          <main
            id="workspace-content"
            tabIndex={-1}
            className="workspace-content"
          >
            {featureError && (
              <p className="notice stale" role="status">
                {t(
                  "暂时无法核对后端功能状态，依赖功能保持关闭。请在功能说明页查看详情。",
                )}
              </p>
            )}
            {view === "home" && (
              <HomeWorkspace
                {...props}
                key={login.account_id}
                accountId={login.account_id}
                features={features}
                onNavigate={navigate}
                onOpenOrder={openOrder}
                onOpenSend={(id) => {
                  setSendAction(id);
                  navigate("management");
                }}
              />
            )}
            {view === "business" && (
              <>
                <div className="page-heading">
                  <div>
                    <h1>{t("业务工作台")}</h1>
                    <p>{t("选一张工单，按「下一步」处理就好。")}</p>
                  </div>
                  {features.create_order && (
                    <button disabled={busy} onClick={() => navigate("create")}>
                      {t("新建工单")}
                    </button>
                  )}
                </div>
                {features.create_order && (
                  <NewRequestBanner
                    csrf={login.csrf_token}
                    onOpen={(id) => {
                      navigate("create");
                      setCreateSuggestion(id);
                    }}
                  />
                )}
                <WorkOrderWorkspace
                  {...props}
                  key={login.account_id}
                  accountId={login.account_id}
                  features={features}
                  initialSelected={selectedOrder}
                  onBusyChange={setBusy}
                  onOpenSend={(id) => {
                    setSendAction(id);
                    navigate("management");
                  }}
                  onConnect={() => navigate("connect")}
                  onOpenApprovals={() => navigate("approvals")}
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
                initialConversation={createConversation}
                initialSuggestion={createSuggestion}
              />
            )}
            {view === "approvals" && (
              <ApprovalsWorkspace
                {...props}
                accountId={login.account_id}
                onBusyChange={setBusy}
                onOpenOrder={openOrder}
              />
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
                accountId={login.account_id}
                features={features}
                onBusyChange={setBusy}
                onCreate={(id) => {
                  navigate("create");
                  setCreateConversation(id);
                }}
                onOpenOrder={openOrder}
                onConnect={() => navigate("connect")}
              />
            )}
            {view === "connect" && (
              <>
                <p className="availability-note">
                  {t(
                    "手动与业务审批发送均需单独授权。AI 润色和自由生成自动回复尚未接通。",
                  )}
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
                initialActionId={sendAction}
              />
            )}
            {view === "guide" && (
              <DeliveryGuide
                features={features}
                error={t(featureError)}
                onOpen={navigate}
                onStartTour={() => setTourOpen(true)}
              />
            )}
          </main>
          {tourOpen && (
            <GuidedTour
              accountId={login.account_id}
              view={view}
              onClose={() => setTourOpen(false)}
            />
          )}
        </div>
      )}
    </div>
  );
}
