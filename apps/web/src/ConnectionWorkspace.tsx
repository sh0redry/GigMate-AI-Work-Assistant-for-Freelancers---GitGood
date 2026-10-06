import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ConnectionError,
  demoConnectionApi,
  liveConnectionApi,
  type Choice,
  type Connector,
  type Issue,
  type Pairing,
  type Selection,
} from "./connection-api";
import "./connection.css";

const states: Record<string, string> = {
  unknown: "状态未知",
  connected: "已连接",
  connecting: "正在连接",
  disconnected: "已断开",
  failed: "连接失败",
  SCAN_QR_CODE: "等待扫码",
  WORKING: "已连接",
  STARTING: "正在连接",
  STOPPED: "连接未启动",
  FAILED: "连接失败",
  PASSKEY_REQUIRED: "需要在手机确认",
  PASSKEY_CONFIRMATION_REQUIRED: "需要在手机确认",
};
const errors: Record<string, string> = {
  CONNECTOR_DISABLED: "尚未配置扫码服务，请按联调文档初始化本机环境。",
  CONNECTOR_CONFIG_INVALID: "连接配置与账号不匹配，请联系接入负责人检查。",
  WAHA_RESOURCE_NOT_FOUND: "WhatsApp 会话尚未创建，点击「启动连接」继续。",
  WAHA_UNAVAILABLE: "WhatsApp 服务暂不可用，请检查服务后刷新。",
  WAHA_RESULT_UNKNOWN: "启动结果未知，请先刷新状态，再决定是否继续。",
  WAHA_NOT_WAITING_FOR_QR: "二维码已失效或扫码完成，请刷新状态。",
  WAHA_NOT_CONNECTED: "WhatsApp 尚未连接，连接后才能发现新会话。",
  VERSION_CONFLICT: "授权已在其他窗口更新。请重新载入并核对，再保存。",
  CHAT_CHOICE_EXPIRED: "会话选项已过期。请重新载入并核对，再保存。",
  UNAUTHENTICATED: "登录已过期，请退出后重新登录。",
};
const mergeChoices = (a: Choice[], b: Choice[]) => [
  ...new Map([...a, ...b].map((c) => [c.choice_id, c])).values(),
];
const sameSelection = (a: string[], b: Choice[]) =>
  a.length === b.length && b.every((c) => a.includes(c.choice_id));

export function ConnectionWorkspace({
  demo = false,
  onSessionExpired,
}: {
  demo?: boolean;
  onSessionExpired?: () => void;
}) {
  const simulator = useMemo(() => (demo ? demoConnectionApi() : null), [demo]);
  const api = useMemo(() => simulator ?? liveConnectionApi(), [simulator]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [statusFetchFailed, setStatusFetchFailed] = useState(false);
  const [id, setId] = useState("");
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [qr, setQr] = useState<string | null>(null);
  const [qrTime, setQrTime] = useState<number | null>(null);
  const [qrAge, setQrAge] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState(false);
  const epoch = useRef(0);
  const statusFailure = useRef(false);
  const qrRef = useRef<string | null>(null);
  const saveAttempt = useRef<{ signature: string; key: string } | null>(null);
  const connector = connectors.find((c) => c.id === id);
  const connected = api.capabilities.pairing
    ? !!pairing?.connected
    : !!connector?.live_connected && !connector.stale && !statusFetchFailed;
  const dirty = !!selection && !sameSelection(picked, selection.selected);
  const clearQr = useCallback(() => {
    if (qrRef.current) URL.revokeObjectURL(qrRef.current);
    qrRef.current = null;
    setQr(null);
    setQrTime(null);
  }, []);
  const report = useCallback(
    (error: unknown) => {
      const e =
        error instanceof ConnectionError
          ? error
          : new ConnectionError(
              "NETWORK_ERROR",
              "无法连接后端，请检查本机服务后重试。",
            );
      setNotice(errors[e.code] ?? e.message);
      setFailure(true);
      if (e.code === "UNAUTHENTICATED") {
        clearQr();
        onSessionExpired?.();
      }
    },
    [clearQr, onSessionExpired],
  );

  const refreshStatus = useCallback(async () => {
    const stamp = epoch.current;
    let list: Connector[];
    try {
      list = await api.connectors();
    } catch (e) {
      if (stamp === epoch.current) {
        statusFailure.current = true;
        setStatusFetchFailed(true);
      }
      throw e;
    }
    if (stamp !== epoch.current) return;
    if (statusFailure.current) {
      setNotice("连接状态查询已恢复。");
      setFailure(false);
    }
    statusFailure.current = false;
    setStatusFetchFailed(false);
    setConnectors(list);
    setStatusLoaded(true);
    const current = list.some((c) => c.id === id) ? id : (list[0]?.id ?? "");
    if (current !== id) {
      setId(current);
      setPairing(null);
      setSelection(null);
      setChoices([]);
      setPicked([]);
      setIssues([]);
      setNextOffset(null);
      saveAttempt.current = null;
      clearQr();
      return;
    }
    if (!current) return;
    if (api.capabilities.pairing) {
      try {
        const p = await api.pairing(current);
        if (stamp !== epoch.current) return;
        setPairing(p);
        if (!p.qr_available) clearQr();
      } catch (e) {
        if (stamp === epoch.current) {
          setPairing(null);
          clearQr();
          report(e);
        }
      }
    }
    const records = await api.issues(current);
    if (stamp === epoch.current) setIssues(records);
  }, [api, id, clearQr, report]);

  useEffect(() => {
    let active = true,
      running = false;
    const update = async () => {
      if (running) return;
      running = true;
      try {
        await refreshStatus();
      } catch (e) {
        if (active) report(e);
      } finally {
        running = false;
      }
    };
    void update();
    const timer = setInterval(() => {
      if (!document.hidden) void update();
    }, 5000);
    return () => {
      active = false;
      clearInterval(timer);
      epoch.current++;
      clearQr();
    };
  }, [refreshStatus, report, clearQr]);

  useEffect(() => {
    const timer = setInterval(
      () => setQrAge(qrTime ? Math.floor((Date.now() - qrTime) / 1000) : 0),
      1000,
    );
    return () => clearInterval(timer);
  }, [qrTime]);

  async function act(task: () => Promise<void>) {
    setBusy(true);
    setNotice("");
    setFailure(false);
    try {
      await task();
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  }
  async function loadSelection() {
    const stamp = epoch.current;
    const value = await api.selection(id);
    if (stamp !== epoch.current) return;
    setSelection(value);
    setPicked(value.selected.map((c) => c.choice_id));
    setChoices(value.selected);
    setNextOffset(null);
    setLoaded(false);
    saveAttempt.current = null;
    if (pairing?.connected) {
      const discovery = await api.chats(id, 0);
      if (stamp !== epoch.current) return;
      setChoices(mergeChoices(value.selected, discovery.items));
      setNextOffset(discovery.next_offset);
      setLoaded(true);
    }
    setNotice(
      demo
        ? "已载入演示授权；取消勾选后保存即可模拟撤销。"
        : "已载入服务端授权；取消勾选后保存即可撤销。",
    );
  }
  async function save(next: string[]) {
    if (!selection) return;
    const stamp = epoch.current;
    const selected = next
      .map((key) => choices.find((c) => c.choice_id === key))
      .filter((c): c is Choice => !!c);
    const signature = JSON.stringify([
      id,
      selection.version,
      selected.map((c) => c.token),
    ]);
    if (saveAttempt.current?.signature !== signature)
      saveAttempt.current = { signature, key: crypto.randomUUID() };
    await api.save(id, selection, selected, saveAttempt.current.key);
    const value = await api.selection(id);
    if (stamp !== epoch.current) return;
    setSelection(value);
    setPicked(value.selected.map((c) => c.choice_id));
    const names = new Map(choices.map((c) => [c.choice_id, c.name]));
    setChoices(
      mergeChoices(
        choices,
        value.selected.map((c) => ({
          ...c,
          name: names.get(c.choice_id) ?? c.name,
        })),
      ),
    );
    saveAttempt.current = null;
    setNotice(
      demo
        ? next.length
          ? `已在演示中保存 ${value.selected.length} 个会话授权，自动回复未开启。`
          : "已在演示中撤销全部会话授权。"
        : next.length
          ? `已保存 ${value.selected.length} 个会话授权，自动回复未开启。`
          : "已撤销全部会话授权，后端将拒绝这些会话的后续消息。",
    );
  }

  return (
    <section
      className="connection-workspace"
      aria-label="WhatsApp 连接与会话授权"
    >
      <div className="connect-heading">
        <div>
          <p className="eyebrow">D-01 · 连接与授权</p>
          <h1>让工作消息，进入你的工作台。</h1>
          <p className="subtle">
            先连接 WhatsApp，再选择允许处理的会话。选择权始终在你手里。
          </p>
        </div>
        <span className="connection-label">
          {demo ? "合成演示" : "本地接入"}
        </span>
      </div>
      {demo && (
        <div className="demo-controls">
          <span>演示模式 · 不连接真实账号、不发送消息</span>
          <div>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  simulator?.connect(true);
                  await refreshStatus();
                  setNotice("模拟扫码成功。接下来载入并选择会话。");
                })
              }
            >
              模拟扫码成功
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  simulator?.connect(false);
                  await refreshStatus();
                })
              }
            >
              模拟断线
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  simulator?.stale();
                  await refreshStatus();
                })
              }
            >
              模拟状态过期
            </button>
          </div>
        </div>
      )}
      <ol className="connection-steps">
        <li className="active">
          <span>01</span>连接 WhatsApp
        </li>
        <li className={connected ? "active" : ""}>
          <span>02</span>选择工作会话
        </li>
        <li className={selection?.selected.length ? "active" : ""}>
          <span>03</span>保存处理授权
        </li>
      </ol>
      <div
        className={`connection-notice ${failure ? "error" : ""}`}
        role={failure ? "alert" : "status"}
        aria-live="polite"
      >
        {notice ||
          (demo
            ? "演示数据仅保留在当前预览中；会话读取授权不会开启自动回复。"
            : "当前可查看连接状态；扫码和会话授权功能待接入。")}
      </div>
      {connectors.length > 1 && (
        <label>
          选择连接
          <select
            value={id}
            disabled={busy || dirty}
            onChange={(e) => {
              epoch.current++;
              clearQr();
              setId(e.target.value);
              setPairing(null);
              setSelection(null);
              setChoices([]);
              setPicked([]);
              setIssues([]);
              setNextOffset(null);
              saveAttempt.current = null;
              setNotice("");
              setFailure(false);
            }}
          >
            {connectors.map((c, i) => (
              <option key={c.id} value={c.id}>
                WhatsApp 连接 {i + 1}
              </option>
            ))}
          </select>
        </label>
      )}
      {!connector ? (
        <div className="panel connection-empty">
          <h2>
            {statusFetchFailed
              ? "连接状态读取失败"
              : !statusLoaded
                ? failure
                  ? "连接状态读取失败"
                  : "正在读取连接状态"
                : "还没有本机连接"}
          </h2>
          <p>
            {statusLoaded
              ? "当前账号暂无连接记录。接入负责人配置完成后，刷新即可查看状态。也可进入「D-01 演示预览」体验扫码与会话选择界面。"
              : "正在向本地服务查询。连接失败时可刷新重试。"}
          </p>
          <button disabled={busy} onClick={() => void act(refreshStatus)}>
            刷新连接
          </button>
        </div>
      ) : (
        <div className="connection-columns">
          <div className="connection-left">
            <section className="panel pairing-panel">
              <div className="section-heading">
                <h2>连接 WhatsApp</h2>
                <span className={`status-dot ${connected ? "online" : ""}`}>
                  {connector.stale || statusFetchFailed
                    ? "状态待确认"
                    : pairing
                      ? (states[pairing.state] ?? "状态未知")
                      : states[connector.state]}
                </span>
              </div>
              <div className={`qr-stage ${connected ? "qr-connected" : ""}`}>
                {!api.capabilities.pairing ? (
                  <>
                    <div className="scan-mark" aria-hidden="true">
                      ⌗
                    </div>
                    <strong>扫码登录待接入</strong>
                    <p>可查看已有连接状态。启动连接及获取二维码暂不可用。</p>
                  </>
                ) : connected ? (
                  <>
                    <div className="connected-mark" aria-hidden="true">
                      ✓
                    </div>
                    <strong>WhatsApp 已连接</strong>
                    <p>无需再次扫码，可选择工作会话。</p>
                  </>
                ) : qr ? (
                  <>
                    <img
                      src={qr}
                      alt="使用手机 WhatsApp 关联设备扫描此二维码"
                    />
                    <small>获取于 {qrAge} 秒前 · 二维码可能失效</small>
                  </>
                ) : (
                  <>
                    <div className="scan-mark" aria-hidden="true">
                      ⌗
                    </div>
                    <strong>{demo ? "扫码界面预览" : "等待获取二维码"}</strong>
                    <p>
                      {demo
                        ? "此区域展示真实二维码的位置"
                        : "启动连接后获取二维码"}
                    </p>
                  </>
                )}
              </div>
              {api.capabilities.pairing && !connected && (
                <ol className="scan-guide">
                  <li>手机打开 WhatsApp → 关联设备</li>
                  <li>选择「关联设备」，扫描这里的二维码</li>
                </ol>
              )}
              <div className="connection-actions">
                <button
                  disabled={
                    busy ||
                    !api.capabilities.pairing ||
                    pairing?.connected ||
                    pairing?.qr_available ||
                    pairing?.state === "STARTING"
                  }
                  onClick={() =>
                    void act(async () => {
                      setPairing(await api.start(id, crypto.randomUUID()));
                      await refreshStatus();
                    })
                  }
                >
                  启动连接
                </button>
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    !api.capabilities.pairing ||
                    !pairing?.qr_available ||
                    demo
                  }
                  onClick={() =>
                    void act(async () => {
                      const stamp = epoch.current;
                      const blob = await api.qr(id);
                      if (stamp !== epoch.current) return;
                      clearQr();
                      const url = URL.createObjectURL(blob);
                      qrRef.current = url;
                      setQr(url);
                      setQrTime(Date.now());
                    })
                  }
                >
                  {qr ? "刷新二维码" : "获取二维码"}
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void act(refreshStatus)}
                >
                  刷新状态
                </button>
              </div>
            </section>
            <section className="panel health-panel">
              <h2>连接与处理状态</h2>
              <dl>
                <div>
                  <dt>WhatsApp 会话</dt>
                  <dd>
                    {connector.live_connected ? "已连接" : "未连接或待确认"}
                  </dd>
                </div>
                <div>
                  <dt>处理链路</dt>
                  <dd>{connector.pipeline_ready ? "采样就绪" : "尚未就绪"}</dd>
                </div>
                <div>
                  <dt>状态新鲜度</dt>
                  <dd>
                    {statusFetchFailed
                      ? "刷新失败，显示上次采样"
                      : connector.stale
                        ? "已过期，需重新检查"
                        : connector.observed_at
                          ? "当前采样有效"
                          : "尚无采样"}
                  </dd>
                </div>
                <div>
                  <dt>最近采样</dt>
                  <dd>
                    {connector.observed_at
                      ? new Date(connector.observed_at).toLocaleString(
                          "zh-CN",
                          {
                            timeZone: "Asia/Hong_Kong",
                            hour12: false,
                          },
                        )
                      : "暂无"}
                  </dd>
                </div>
                <div>
                  <dt>接收授权</dt>
                  <dd>{connector.enabled ? "已启用" : "已暂停"}</dd>
                </div>
                <div>
                  <dt>故障核对</dt>
                  <dd>
                    {connector.review_required
                      ? `${connector.unresolved_issues} 项待核对`
                      : "无待核对项"}
                  </dd>
                </div>
              </dl>
              {issues
                .filter((i) => !i.acknowledged_at)
                .map((i) => (
                  <div className="issue-note" key={i.id}>
                    待核对：{i.code}
                    <small>
                      恢复连接不会自动清除历史缺口，需由操作者核对。
                    </small>
                  </div>
                ))}
            </section>
          </div>
          <section className="panel conversation-panel">
            <div className="section-heading">
              <div>
                <h2>选择工作会话</h2>
                <p className="subtle">勾选后保存，才会授权后端处理消息。</p>
              </div>
              <span className="selection-count">
                {api.capabilities.selection
                  ? `${picked.length} 已勾选`
                  : "授权待查询"}
              </span>
            </div>
            <div className="conversation-toolbar">
              <button
                className="secondary"
                disabled={busy || dirty || !api.capabilities.selection}
                onClick={() => void act(loadSelection)}
              >
                {selection ? "重新载入会话" : "载入会话与授权"}
              </button>
              {selection && (
                <small>
                  {demo ? "演示版本" : "服务端版本"} {selection.version} ·{" "}
                  {selection.selected.length} 个已授权
                </small>
              )}
            </div>
            {!selection ? (
              <div className="conversation-empty">
                <span aria-hidden="true">☷</span>
                <h3>
                  {api.capabilities.selection
                    ? "你的会话由你选择"
                    : "会话选择待接入"}
                </h3>
                <p>
                  {api.capabilities.selection
                    ? "连接后载入会话。已有授权在断线时也可以撤销。"
                    : "目前无法查询或更改会话授权。可在演示预览中体验选择流程。"}
                </p>
                {!api.capabilities.selection && (
                  <div className="connection-actions">
                    <button disabled>保存会话授权</button>
                    <button className="secondary" disabled>
                      撤销全部授权
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <>
                {!choices.length && (
                  <div className="conversation-empty">
                    <h3>暂无会话</h3>
                    <p>
                      {loaded
                        ? "可在手机创建测试聊天后重新载入。"
                        : "尚未连接；当前没有已授权会话。"}
                    </p>
                  </div>
                )}
                <div className="chat-choices">
                  {choices.map((c, i) => (
                    <label className="chat-choice" key={c.choice_id}>
                      <input
                        type="checkbox"
                        checked={picked.includes(c.choice_id)}
                        disabled={
                          busy ||
                          (!picked.includes(c.choice_id) &&
                            picked.length >= 100)
                        }
                        onChange={(e) => {
                          setPicked((p) =>
                            e.target.checked
                              ? [...p, c.choice_id]
                              : p.filter((k) => k !== c.choice_id),
                          );
                          setNotice("");
                        }}
                      />
                      <span className="chat-avatar" aria-hidden="true">
                        {c.kind === "group" ? "群" : c.name.slice(0, 1)}
                      </span>
                      <span className="chat-title">
                        <strong>
                          {c.name === "已授权会话"
                            ? `已授权会话 ${i + 1}`
                            : c.name}
                        </strong>
                        <small>
                          {c.kind === "group" ? "群聊" : "个人会话"} ·{" "}
                          {selection.selected.some(
                            (s) => s.choice_id === c.choice_id,
                          )
                            ? demo
                              ? "演示已授权"
                              : "服务端已授权"
                            : "尚未授权"}
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
                {nextOffset !== null && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      void act(async () => {
                        const discovery = await api.chats(id, nextOffset);
                        setChoices((c) => mergeChoices(c, discovery.items));
                        setNextOffset(discovery.next_offset);
                      })
                    }
                  >
                    加载更多会话
                  </button>
                )}
                <div className="authorization-summary">
                  <strong>
                    {dirty
                      ? "有尚未保存的更改"
                      : demo
                        ? "授权已保存在当前演示中"
                        : "授权已与服务端同步"}
                  </strong>
                  <p>
                    授权仅用于读取和处理选中会话。不授权自动回复，不改变正式工单。
                  </p>
                </div>
                <div className="connection-actions">
                  <button
                    disabled={busy || !dirty}
                    onClick={() => void act(() => save(picked))}
                  >
                    {busy ? "处理中…" : "保存会话授权"}
                  </button>
                  <button
                    className="secondary"
                    disabled={busy || !selection.selected.length}
                    onClick={() => void act(() => save([]))}
                  >
                    撤销全部授权
                  </button>
                  <button
                    className="secondary"
                    disabled={busy || !dirty}
                    onClick={() => {
                      setPicked(selection.selected.map((c) => c.choice_id));
                      setNotice("已放弃未保存的更改。");
                    }}
                  >
                    放弃更改
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
