import { useCallback, useEffect, useMemo, useRef } from "react";
import { useStableState as useState } from "./useStableState";
import { t, localized } from "./i18n.ts";
import { conversationApi, MAX_CONVERSATION_PAGES } from "./conversation-api";
import { type Choice, type Connector } from "./connection-api";
import { privateReadDenied } from "./read-cache";
import type { TimelineMessage } from "./waha-sync-api";
import {
  orderedMessages,
  nearConversationBottom,
  messageSummary,
  sourceMatch,
  type ConversationIntent,
} from "./conversation-view";
import { WahaSend } from "./WahaSend";
import { WahaMedia } from "./WahaMedia";
import { usePolling } from "./usePolling";
import { ConversationBusiness } from "./ConversationBusiness";
import type { Features } from "./features";

const delivery = localized({
  unknown: "未知",
  sent: "已发出",
  delivered: "已送达",
  read: "已读",
});
type Window = {
  scope: string;
  items: TimelineMessage[];
  cursor: string | null;
  pages: number;
  truncated: boolean;
  observed: string;
};
const emptyWindow: Window = {
  scope: "",
  items: [],
  cursor: null,
  pages: 1,
  truncated: false,
  observed: "",
};

export function CustomerConversations({
  csrf,
  active: visible,
  features,
  intent,
  onSessionExpired,
  onBusyChange,
  onOpenOrder,
  onCreate,
  onConnect,
}: {
  csrf: string;
  active: boolean;
  features: Features;
  intent?: ConversationIntent;
  onSessionExpired: () => void;
  onBusyChange: (busy: boolean) => void;
  onOpenOrder: (id: string) => void;
  onCreate: (
    conversationId: string,
    sources: { message_id: string; message_revision: number }[],
  ) => void;
  onConnect: () => void;
}) {
  const api = useMemo(() => conversationApi(csrf), [csrf]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [connectorReady, setConnectorReady] = useState(false);
  const [connection, setConnection] = useState("");
  const [catalog, setCatalog] = useState<{
    scope: string;
    items: Choice[];
    ready: boolean;
  }>({ scope: "", items: [], ready: false });
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("all");
  const [listPage, setListPage] = useState(0);
  const [previews, setPreviews] = useState<
    Record<string, TimelineMessage | null>
  >({});
  const [windowData, setWindow] = useState<Window>(emptyWindow);
  const [stale, setStale] = useState(true);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [composerBlocked, setComposerBlocked] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [timelineRefresh, setTimelineRefresh] = useState(0);
  const [suspended, setSuspended] = useState(false);
  const accessStopped = useRef(false);
  const stopped = useCallback(() => accessStopped.current, []);
  const historyRefreshedAt = useRef(0);
  const [newCount, setNewCount] = useState(0);
  const [highlight, setHighlight] = useState("");
  const [sourceNotice, setSourceNotice] = useState("");
  const [pendingSource, setPendingSource] = useState<{
    id: string;
    revision: number;
    scope: string;
  } | null>(null);
  const sourceTarget = useRef<{ id: string; revision: number } | null>(null);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [openedMedia, setOpenedMedia] = useState("");
  const [showBusiness, setShowBusiness] = useState(true);
  const [composerInput, setComposerInput] = useState<
    | {
        token: string;
        text?: string;
        replyId?: string;
        mode?: "manual" | "agent_assisted";
      }
    | undefined
  >(undefined);
  const [texts, setTexts] = useState<
    Record<string, { text: string; mode: "manual" | "agent_assisted" }>
  >({});
  const [mobileList, setMobileList] = useState(true);
  const scroller = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const position = useRef<{
    top: number;
    height: number;
    bottom: boolean;
    prepend: boolean;
  } | null>(null);
  const current = useRef<Window>(emptyWindow);
  const requestedPages = useRef(1);
  const seen = useRef(new Map<string, string>());
  const handledIntent = useRef("");
  const rememberSeen = useCallback((key: string, id: string) => {
    seen.current.delete(key);
    seen.current.set(key, id);
    if (seen.current.size > 256)
      seen.current.delete(seen.current.keys().next().value!);
  }, []);
  const choices = catalog.scope === connection ? catalog.items : [];
  const chat = choices.find((value) => value.id === selected);
  const scope = `${connection}:${selected}`;
  const messages = windowData.scope === scope ? windowData.items : [];
  const connector = connectors.find((value) => value.id === connection);
  const ready =
    !!chat &&
    connectorReady &&
    catalog.ready &&
    !stale &&
    !!connector?.enabled &&
    connector.live_connected &&
    !connector.stale &&
    connector.pipeline_ready !== false;
  const conversation = chat?.conversation_id ?? messages[0]?.conversation_id;
  const filtered = choices.filter(
    (value) =>
      (kind === "all" || value.kind === kind) &&
      value.label.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
  );
  const visibleChoices = filtered.slice(listPage * 8, listPage * 8 + 8);
  const visibleIds = visibleChoices.map((value) => value.id).join(":");
  const handleBusy = useCallback(
    (value: boolean) => {
      setBusy(value);
      onBusyChange(value);
    },
    [onBusyChange],
  );
  const clearPrivate = useCallback(() => {
    setSelected("");
    seen.current.clear();
    setCatalog({ scope: "", items: [], ready: false });
    setWindow(emptyWindow);
    current.current = emptyWindow;
    setPreviews({});
    setTexts({});
    setComposerInput(undefined);
    setComposerBlocked(false);
    setSelectedSources([]);
    setPendingSource(null);
    setSourceNotice("");
    sourceTarget.current = null;
  }, []);

  const report = useCallback(
    (error: unknown) => {
      if ((error as { code?: string }).code === "UNAUTHENTICATED")
        onSessionExpired();
      if (privateReadDenied(error)) {
        accessStopped.current = true;
        setSuspended(true);
        setConnectorReady(false);
        setStale(true);
        clearPrivate();
      }
      setNotice(error instanceof Error ? error.message : t("查询失败"));
    },
    [onSessionExpired, clearPrivate],
  );
  const refreshAll = () => {
    accessStopped.current = false;
    setSuspended(false);
    requestedPages.current = 1;
    historyRefreshedAt.current = 0;
    setRefresh((old) => old + 1);
  };

  const readConnectors = useCallback(
    async (signal: AbortSignal) => {
      try {
        const result = await api.connectors(signal);
        if (signal.aborted || stopped()) return;
        setConnectors(result.items);
        setConnectorReady(true);
        setConnection((old) =>
          result.items.some((value) => value.id === old)
            ? old
            : (result.items[0]?.id ?? ""),
        );
        if (result.partial)
          setNotice(t("仅展示本次有界查询结果，列表可能不完整。"));
      } catch (error) {
        if (!signal.aborted && !stopped()) {
          setStale(true);
          setConnectorReady(false);
          if (privateReadDenied(error)) setConnectors([]);
        }
        throw error;
      }
    },
    [api, refresh, stopped],
  );
  usePolling(readConnectors, 15000, visible && !suspended, report, stopped);

  const readChats = useCallback(
    async (signal: AbortSignal) => {
      try {
        const items = await api.chats(connection, signal);
        if (signal.aborted || stopped()) return;
        setCatalog({ scope: connection, items, ready: true });
        setSelected((old) =>
          items.some((value) => value.id === old) ? old : "",
        );
        const allowed = new Set(
          items.map((value) => `${connection}:${value.id}`),
        );
        for (const key of seen.current.keys()) {
          if (key.startsWith(connection + ":") && !allowed.has(key))
            seen.current.delete(key);
        }
      } catch (error) {
        if (!signal.aborted && !stopped()) {
          setCatalog((old) => ({ ...old, ready: false }));
          setStale(true);
        }
        throw error;
      }
    },
    [api, connection, refresh, stopped],
  );
  usePolling(
    readChats,
    15000,
    visible && !!connection && !suspended,
    report,
    stopped,
  );

  const choose = useCallback(
    (id: string) => {
      if (busy) return;
      setSelected(id);
      setStale(true);
      setHighlight("");
      setNewCount(0);
      setSelectedSources([]);
      setOpenedMedia("");
      setComposerInput(undefined);
      setMobileList(false);
      requestedPages.current = 1;
      current.current = emptyWindow;
      setPendingSource(null);
      setSourceNotice("");
      sourceTarget.current = null;
      atBottom.current = true;
      position.current = null;
      setNotice("");
      historyRefreshedAt.current = 0;
    },
    [busy],
  );
  useEffect(() => {
    if (
      !visible ||
      !intent ||
      handledIntent.current === intent.token ||
      !catalog.ready
    )
      return;
    const target = choices.find(
      (value) => value.conversation_id === intent.conversationId,
    );
    if (target) {
      choose(target.id);
      handledIntent.current = intent.token;
      if (intent.messageId && intent.revision)
        setPendingSource({
          id: intent.messageId,
          revision: intent.revision,
          scope: `${connection}:${target.id}`,
        });
    } else if (connection)
      setNotice(t("关联会话未授权或旧后端缺少映射，请核对连接与后端版本。"));
  }, [intent, catalog, visible, connection, choose]);

  const readTimeline = useCallback(
    async (signal: AbortSignal) => {
      if (!chat) return;
      try {
        const previous =
          current.current.scope === scope ? current.current : emptyWindow;
        const full =
          requestedPages.current > 0 ||
          Date.now() - historyRefreshedAt.current >= 30000;
        const result = await api.timeline(
          connection,
          chat!,
          full ? Math.max(requestedPages.current, previous.pages) : 1,
          full ? previous.items[0]?.id : previous.items.at(-1)?.id,
          signal,
        );
        if (signal.aborted || stopped()) return;
        if (full) {
          requestedPages.current = 0;
          historyRefreshedAt.current = Date.now();
        }
        const updated =
          full || result.truncated
            ? result
            : {
                ...result,
                items: orderedMessages([
                  ...previous.items,
                  ...result.items,
                ]).slice(-500),
                cursor: previous.cursor,
                pages: Math.min(
                  MAX_CONVERSATION_PAGES,
                  Math.max(
                    previous.pages,
                    Math.ceil(
                      (previous.items.length +
                        result.items.filter(
                          (m) => !previous.items.some((old) => old.id === m.id),
                        ).length) /
                        50,
                    ),
                  ),
                ),
              };
        const element = scroller.current;
        if (element)
          position.current = {
            top: element.scrollTop,
            height: element.scrollHeight,
            bottom: atBottom.current,
            prepend:
              !!previous.items.length &&
              !!updated.items.length &&
              updated.items[0].occurred_at < previous.items[0].occurred_at,
          };
        const last = previous.items.at(-1);
        const additions = last
          ? updated.items.filter(
              (m) =>
                !previous.items.some((old) => old.id === m.id) &&
                (m.occurred_at > last.occurred_at ||
                  (m.occurred_at === last.occurred_at && m.id > last.id)),
            ).length
          : 0;
        if (additions && !atBottom.current)
          setNewCount((old) => old + additions);
        const value = { ...updated, scope, observed: new Date().toISOString() };
        current.current = value;
        setWindow(value);
        setStale(false);
        setNotice("");
        setSelectedSources((old) =>
          old.filter((key) =>
            updated.items.some(
              (m) =>
                `${m.id}:${m.revision}` === key &&
                !m.revoked &&
                m.evidence === "revision",
            ),
          ),
        );
        if (updated.items.length) rememberSeen(scope, updated.items.at(-1)!.id);
        if (result.truncated)
          setNotice(
            t("消息更新超过本次显示上限，请核对近期消息；未声称历史完整。"),
          );
      } catch (error) {
        if (!signal.aborted && !stopped()) setStale(true);
        throw error;
      }
    },
    [
      api,
      connection,
      chat?.id,
      refresh,
      timelineRefresh,
      stopped,
      rememberSeen,
    ],
  );
  usePolling(
    readTimeline,
    3000,
    visible && !!chat && catalog.ready && !suspended,
    report,
    stopped,
  );

  useEffect(() => {
    const element = scroller.current,
      saved = position.current;
    if (!element || !saved) return;
    if (saved.bottom) element.scrollTop = element.scrollHeight;
    else if (saved.prepend)
      element.scrollTop = saved.top + element.scrollHeight - saved.height;
    position.current = null;
  }, [windowData]);

  const readPreviews = useCallback(
    async (signal: AbortSignal) => {
      const results = await Promise.allSettled(
        visibleChoices.map(async (choice) => {
          try {
            return {
              id: `${connection}:${choice.id}`,
              message:
                (
                  await api.timeline(connection, choice, 1, undefined, signal)
                ).items.at(-1) ?? null,
            };
          } catch (error) {
            // A fast denial must clear private data even if another preview is slow.
            if (!signal.aborted && !stopped() && privateReadDenied(error))
              report(error);
            throw error;
          }
        }),
      );
      if (signal.aborted || stopped()) return;
      const updates: Record<string, TimelineMessage | null> = {};
      let failed: unknown;
      for (const result of results) {
        if (result.status === "fulfilled") {
          updates[result.value.id] = result.value.message;
          if (result.value.message && !seen.current.has(result.value.id)) {
            rememberSeen(result.value.id, result.value.message.id);
          }
        } else {
          if (privateReadDenied(result.reason)) throw result.reason;
          failed = result.reason;
        }
      }
      setPreviews((old) => ({ ...old, ...updates }));
      if (failed) throw failed;
    },
    [api, connection, visibleIds, refresh, stopped, report, rememberSeen],
  );
  usePolling(
    readPreviews,
    15000,
    visible &&
      !!connection &&
      catalog.ready &&
      !!visibleChoices.length &&
      !suspended,
    report,
    stopped,
  );

  function locate(id: string, revision: number) {
    setPendingSource({ id, revision, scope });
  }
  useEffect(() => {
    if (
      !visible ||
      !pendingSource ||
      pendingSource.scope !== scope ||
      windowData.scope !== scope ||
      stale
    )
      return;
    const { id, revision } = pendingSource;
    const exact = messages.find((message) =>
      sourceMatch(message, id, revision),
    );
    const changed = messages.find(
      (message) => message.source_message_id === id,
    );
    if (exact || changed) {
      const value = exact ?? changed!;
      setHighlight(value.id);
      sourceTarget.current = { id, revision };
      setSourceNotice(
        exact
          ? ""
          : t("原依据已修改或撤回，当前气泡不是原版本的有效确认依据。"),
      );
      document
        .getElementById(`conversation-message-${value.id}`)
        ?.scrollIntoView({ block: "center" });
      atBottom.current = false;
      requestedPages.current = 0;
      setPendingSource(null);
    } else if (windowData.cursor && windowData.pages < MAX_CONVERSATION_PAGES) {
      requestedPages.current = MAX_CONVERSATION_PAGES;
      setTimelineRefresh((old) => old + 1);
      setSourceNotice(t("正在有界查找较早来源；历史快照不能代替客户确认。"));
    } else {
      setSourceNotice(
        t("本次窗口未找到该来源，请到工单核对记录或明确导入近期历史。"),
      );
      setPendingSource(null);
    }
  }, [windowData, pendingSource, visible, stale]);
  useEffect(() => {
    const target = sourceTarget.current;
    if (
      target &&
      messages.some(
        (m) =>
          m.source_message_id === target.id &&
          !sourceMatch(m, target.id, target.revision),
      )
    )
      setSourceNotice(
        t("原依据已修改或撤回，当前气泡不是原版本的有效确认依据。"),
      );
  }, [windowData]);
  const chosen = messages.filter(
    (message) =>
      selectedSources.includes(`${message.id}:${message.revision}`) &&
      message.source_message_id &&
      message.revision &&
      !message.revoked &&
      message.evidence === "revision" &&
      message.origin === "live" &&
      message.direction === "incoming",
  );

  return (
    <section
      className="customer-conversations"
      hidden={!visible}
      aria-label={t("客户会话")}
      data-mobile-list={mobileList}
    >
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t("客户会话")}</p>
          <h1>{t("对话、回复与工单，在同一处。")}</h1>
          <p>
            {t("仅显示已授权会话；新消息通常每 3 秒检查，历史可能不完整。")}
          </p>
        </div>
        <button className="secondary" disabled={busy} onClick={onConnect}>
          {t("连接与会话授权")}
        </button>
      </div>
      {suspended && (
        <button className="secondary" disabled={busy} onClick={refreshAll}>
          {t("刷新会话")}
        </button>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {sourceNotice && (
        <p className="notice" role="status">
          {sourceNotice}
        </p>
      )}
      {!connectors.length && (
        <div className="panel">
          <p>{t("当前安装没有可用连接，请先配置并授权工作会话。")}</p>
          <button onClick={onConnect}>{t("连接与会话授权")}</button>
        </div>
      )}
      {connectors.length > 0 && (
        <>
          <label>
            {t("当前连接")}
            <select
              value={connection}
              disabled={busy}
              onChange={(e) => {
                setConnection(e.target.value);
                choose("");
                setListPage(0);
                setPreviews({});
              }}
            >
              {connectors.map((value, index) => (
                <option key={value.id} value={value.id}>
                  {t("会话 {0}", index + 1)} · {value.state}
                </option>
              ))}
            </select>
          </label>
          <div className="conversation-layout" data-business={showBusiness}>
            <aside className="conversation-list" aria-label={t("已授权聊天")}>
              <h2>{t("已授权聊天")}</h2>
              <label>
                {t("搜索客户会话")}
                <input
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setListPage(0);
                  }}
                />
              </label>
              <label>
                {t("会话类型")}
                <select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value);
                    setListPage(0);
                  }}
                >
                  <option value="all">{t("全部")}</option>
                  <option value="direct">{t("个人聊天")}</option>
                  <option value="group">{t("群聊")}</option>
                </select>
              </label>
              {!choices.length && (
                <p>{t("没有已授权工作会话，请先选择并保存处理授权。")}</p>
              )}
              {visibleChoices.map((choice) => {
                const key = `${connection}:${choice.id}`,
                  preview = previews[key];
                return (
                  <button
                    className="conversation-choice secondary"
                    key={choice.id}
                    aria-pressed={selected === choice.id}
                    disabled={busy}
                    onClick={() => choose(choice.id)}
                  >
                    <strong>{choice.label}</strong>
                    <small>
                      {choice.kind === "group" ? t("群聊") : t("个人聊天")}
                    </small>
                    <span>
                      {preview?.revoked
                        ? t("此消息已撤回")
                        : messageSummary(preview ?? undefined) ||
                          t("尚无可显示消息")}
                    </span>
                    {preview && (
                      <time dateTime={preview.occurred_at}>
                        {new Date(preview.occurred_at).toLocaleString()}
                      </time>
                    )}
                    {preview &&
                      seen.current.has(key) &&
                      seen.current.get(key) !== preview.id && (
                        <span className="badge">{t("GigMate 内有新消息")}</span>
                      )}
                  </button>
                );
              })}
              <div className="conversation-pagination">
                <button
                  className="secondary"
                  disabled={!listPage || busy}
                  onClick={() => setListPage((old) => old - 1)}
                >
                  {t("上一页")}
                </button>
                <span>{listPage + 1}</span>
                <button
                  className="secondary"
                  disabled={(listPage + 1) * 8 >= filtered.length || busy}
                  onClick={() => setListPage((old) => old + 1)}
                >
                  {t("下一页")}
                </button>
              </div>
              <small>
                {t(
                  "新消息标记仅属于 GigMate；查看不会自动发送 WhatsApp 已读回执。",
                )}
              </small>
            </aside>
            <div className="conversation-main">
              {!chat ? (
                <div className="panel">
                  <h2>{t("选择客户，开始处理对话")}</h2>
                  <p>{t("左侧选择已授权聊天，即可读取近期消息并准备回复。")}</p>
                </div>
              ) : (
                <>
                  <header className="conversation-header">
                    <button
                      className="secondary conversation-back"
                      disabled={busy}
                      onClick={() => setMobileList(true)}
                    >
                      {t("返回会话列表")}
                    </button>
                    <h2>{chat.label}</h2>
                    <button
                      className="secondary"
                      onClick={() => setShowBusiness((old) => !old)}
                    >
                      {showBusiness ? t("收起工单侧栏") : t("显示工单侧栏")}
                    </button>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={refreshAll}
                    >
                      {t("刷新会话")}
                    </button>
                  </header>
                  <p role="status">
                    {stale
                      ? t("同步状态待核对，发送保持关闭。")
                      : t(
                          "已同步至 {0}",
                          new Date(windowData.observed).toLocaleTimeString(),
                        )}
                    {!ready &&
                      !stale &&
                      ` · ${t("当前连接未就绪，仍可核对已允许读取的记录。")}`}
                  </p>
                  <div
                    className="conversation-scroll"
                    ref={scroller}
                    role="region"
                    aria-label={t("当前聊天消息")}
                    tabIndex={0}
                    onScroll={() => {
                      if (scroller.current)
                        atBottom.current = nearConversationBottom(
                          scroller.current,
                        );
                    }}
                  >
                    {windowData.scope === scope && windowData.cursor && (
                      <button
                        className="secondary"
                        disabled={
                          busy ||
                          stale ||
                          windowData.pages >= MAX_CONVERSATION_PAGES
                        }
                        onClick={() => {
                          requestedPages.current = windowData.pages + 1;
                          setTimelineRefresh((old) => old + 1);
                        }}
                      >
                        {t("加载更早消息")}
                      </button>
                    )}
                    {windowData.pages >= MAX_CONVERSATION_PAGES &&
                      windowData.cursor && (
                        <p>
                          {t(
                            "已达本次窗口上限，请在连接页明确导入或核对更早记录。",
                          )}
                        </p>
                      )}
                    {!messages.length && (
                      <p>{t("尚无可显示消息；未接收的旧聊天不会自动补齐。")}</p>
                    )}
                    {messages.map((message) => (
                      <article
                        key={message.id}
                        id={`conversation-message-${message.id}`}
                        className="conversation-message"
                        data-direction={message.direction}
                        data-highlight={highlight === message.id}
                      >
                        <div className="conversation-bubble">
                          <small>
                            {message.direction === "incoming"
                              ? t("顾客")
                              : t("商户")}{" "}
                            · {new Date(message.occurred_at).toLocaleString()} ·{" "}
                            {message.origin === "history"
                              ? t("历史快照")
                              : t("实时接入")}
                            {message.revision && message.revision > 1
                              ? ` · ${t("修订 {0}", message.revision)}`
                              : ""}
                          </small>
                          {message.sender_id && (
                            <small>
                              {t("群成员标识：")}
                              {message.sender_id.slice(-8)}
                            </small>
                          )}
                          {message.reply_to_id && (
                            <button
                              className="secondary"
                              onClick={() => {
                                const element = document.getElementById(
                                  `conversation-message-${message.reply_to_id}`,
                                );
                                if (element) {
                                  setHighlight(message.reply_to_id!);
                                  element.scrollIntoView({ block: "center" });
                                } else
                                  setNotice(
                                    t(
                                      "引用消息不在本次窗口内，请先加载更早消息。",
                                    ),
                                  );
                              }}
                            >
                              {t("查看引用消息")}
                            </button>
                          )}
                          <p className="conversation-text">
                            {message.revoked
                              ? t("此消息已撤回")
                              : (message.text ??
                                message.filename ??
                                t("无文字内容"))}
                          </p>
                          {message.kind !== "text" && !message.revoked && (
                            <>
                              <button
                                className="secondary"
                                disabled={stale}
                                onClick={() =>
                                  setOpenedMedia((old) =>
                                    old === message.id ? "" : message.id,
                                  )
                                }
                              >
                                {t("附件预览与识别")}
                              </button>
                              {openedMedia === message.id && (
                                <WahaMedia
                                  key={message.id}
                                  csrf={csrf}
                                  connection={connection}
                                  snapshot={message.id}
                                  mimetype={
                                    message.mimetype
                                      ?.split(";")[0]
                                      .trim()
                                      .toLowerCase() ?? null
                                  }
                                  enabled={ready}
                                  onSessionExpired={onSessionExpired}
                                />
                              )}
                            </>
                          )}
                          {message.delivery_status && (
                            <small>
                              {t("送达状态：")}
                              {delivery[message.delivery_status]}
                            </small>
                          )}
                          {!message.revoked && (
                            <div className="conversation-message-actions">
                              <button
                                className="secondary"
                                disabled={busy || !ready || composerBlocked}
                                onClick={() =>
                                  setComposerInput({
                                    token: crypto.randomUUID(),
                                    replyId: message.id,
                                  })
                                }
                              >
                                {t("引用回复")}
                              </button>
                              {message.origin === "live" &&
                                message.evidence === "revision" &&
                                message.source_message_id &&
                                message.direction === "incoming" &&
                                message.text && (
                                  <label>
                                    <input
                                      type="checkbox"
                                      checked={selectedSources.includes(
                                        `${message.id}:${message.revision}`,
                                      )}
                                      disabled={stale || busy}
                                      onChange={(e) =>
                                        setSelectedSources((old) =>
                                          e.target.checked
                                            ? [
                                                ...old,
                                                `${message.id}:${message.revision}`,
                                              ]
                                            : old.filter(
                                                (id) =>
                                                  id !==
                                                  `${message.id}:${message.revision}`,
                                              ),
                                        )
                                      }
                                    />
                                    {t("选作工单来源")}
                                  </label>
                                )}
                            </div>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                  {newCount > 0 && (
                    <button
                      className="conversation-new"
                      onClick={() => {
                        if (scroller.current)
                          scroller.current.scrollTop =
                            scroller.current.scrollHeight;
                        atBottom.current = true;
                        setNewCount(0);
                      }}
                    >
                      {t("查看 {0} 条新消息", newCount)}
                    </button>
                  )}
                  <div className="conversation-source-actions">
                    <span>{t("已选 {0} 条有效客户来源", chosen.length)}</span>
                    <button
                      className="secondary"
                      disabled={
                        busy ||
                        !ready ||
                        !features.create_order ||
                        !conversation ||
                        !chosen.length
                      }
                      onClick={() =>
                        onCreate(
                          conversation!,
                          chosen.map((m) => ({
                            message_id: m.source_message_id!,
                            message_revision: m.revision!,
                          })),
                        )
                      }
                    >
                      {t("从所选消息核对新建工单")}
                    </button>
                  </div>
                  <details className="conversation-composer" open>
                    <summary>{t("准备回复与核对发送")}</summary>
                    <WahaSend
                      key={scope}
                      compact
                      onComposerBlockedChange={setComposerBlocked}
                      connection={connection}
                      csrf={csrf}
                      chat={chat.id}
                      label={chat.label}
                      enabled={ready}
                      messages={messages}
                      initialText={texts[scope]?.text ?? ""}
                      initialMode={texts[scope]?.mode ?? "manual"}
                      composerInput={composerInput}
                      onTextChange={(text, mode) =>
                        setTexts((old) => ({ ...old, [scope]: { text, mode } }))
                      }
                      onBusyChange={handleBusy}
                      onSessionExpired={onSessionExpired}
                    />
                  </details>
                </>
              )}
            </div>
            {chat && showBusiness && conversation && (
              <ConversationBusiness
                key={scope}
                csrf={csrf}
                conversation={conversation}
                messages={messages}
                enabled={ready && !composerBlocked}
                busy={busy}
                onBusyChange={handleBusy}
                onOpenOrder={onOpenOrder}
                onLocate={locate}
                onAdopt={(text) =>
                  setComposerInput({
                    token: crypto.randomUUID(),
                    text,
                    mode: "agent_assisted",
                  })
                }
                onSessionExpired={onSessionExpired}
              />
            )}
            {chat && showBusiness && !conversation && (
              <aside className="conversation-business">
                <p>
                  {t("当前后端缺少会话映射，工单关联保持关闭；仍可读取消息。")}
                </p>
              </aside>
            )}
          </div>
        </>
      )}
    </section>
  );
}
