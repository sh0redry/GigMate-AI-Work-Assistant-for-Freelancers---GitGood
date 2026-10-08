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
import { connectionState, pendingIssues } from "./connection-state";

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
  WAHA_RESOURCE_NOT_FOUND: "WhatsApp 会话尚未创建，请先准备本机服务后刷新。",
  WAHA_UNAVAILABLE: "WhatsApp 服务暂不可用，请检查服务后刷新。",
  WAHA_ENGINE_MISMATCH:
    "本机会话未启动或服务引擎信息不匹配，请联系接入负责人恢复服务后刷新。",
  WAHA_NOT_WAITING_FOR_QR: "二维码已失效或扫码完成，请刷新状态。",
  WAHA_NOT_CONNECTED: "WhatsApp 尚未连接，连接后才能发现新会话。",
  VERSION_CONFLICT: "授权已在其他窗口更新。请重新载入并核对，再保存。",
  CHAT_CHOICE_EXPIRED: "会话选项已过期。请重新载入并核对，再保存。",
  UNAUTHENTICATED: "登录已过期，请退出后重新登录。",
  LOCAL_PAIRING_UNAVAILABLE:
    "无法读取本机扫码服务，请检查 Docker 和本地环境后刷新。",
  LOCAL_PAIRING_BUSY: "正在获取本机二维码，请稍后刷新。",
  LOCAL_BINDING_MISMATCH: "当前连接与本机配置不匹配，请联系接入负责人检查。",
  LOCAL_CONFIG_INVALID_OR_MISSING:
    "本机扫码环境尚未配置，请按联调文档准备后刷新。",
  CONSENT_REVOKED: "连接授权已暂停，二维码已隐藏。",
  LOCAL_PYTHON_UNAVAILABLE:
    "未找到项目 Python 环境，请按本地启动指南准备 .venv。",
  LOCAL_PAIRING_DEPENDENCIES_MISSING:
    "项目 Python 依赖缺失，请按本地启动指南安装锁定依赖。",
  CSRF_INVALID: "本机操作验证失败，请退出后重新登录。",
  CSRF_REJECTED: "本机操作验证失败，请退出后重新登录。",
  WAHA_RESULT_UNKNOWN:
    "重连结果尚不确定。请刷新状态核对，不要重复重连；仍无法确认时请联系接入负责人。",
  LOCAL_OPERATION_RESULT_UNKNOWN:
    "操作结果尚不确定，请刷新状态核对，暂勿重复操作。",
  WAHA_RECOVERY_NOT_REQUIRED: "会话状态已变化，无需重连。请刷新状态。",
  LOCAL_RESTART_COOLDOWN: "刚刚已请求重连，请等待至少 30 秒并刷新状态。",
  COMPONENT_STILL_UNAVAILABLE: "所选故障尚未恢复，不能清除。请刷新后检查。",
  REVIEW_CONFIRMATION_REQUIRED: "请先核对故障时段，并确认无需导入历史消息。",
  REVIEW_ALREADY_RECORDED:
    "此故障已有其他核对结论，请刷新后检查，不能覆盖原结论。",
};
const mergeChoices = (a: Choice[], b: Choice[]) => [
  ...new Map([...a, ...b].map((c) => [c.choice_id, c])).values(),
];
const sameSelection = (a: string[], b: Choice[]) =>
  a.length === b.length && b.every((c) => a.includes(c.choice_id));
const issueLabels: Record<string, string> = {
  MONITOR_GAP: "监测中断时段",
  PROVIDER_UNAVAILABLE: "WhatsApp 服务不可用",
  API_UNAVAILABLE: "接入服务不可用",
  WORKER_UNAVAILABLE: "消息处理服务不可用",
};

export function ConnectionWorkspace({
  demo = false,
  csrf = "",
  onSessionExpired,
}: {
  demo?: boolean;
  csrf?: string;
  onSessionExpired?: () => void;
}) {
  const simulator = useMemo(() => (demo ? demoConnectionApi() : null), [demo]);
  const api = useMemo(
    () => simulator ?? liveConnectionApi(csrf),
    [simulator, csrf],
  );
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [statusFetchFailed, setStatusFetchFailed] = useState(false);
  const [pairingFetchFailed, setPairingFetchFailed] = useState(false);
  const [id, setId] = useState("");
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [reviewSnapshot, setReviewSnapshot] = useState<string[]>([]);
  const [issuesFetchFailed, setIssuesFetchFailed] = useState(false);
  const [issuesLoaded, setIssuesLoaded] = useState(false);
  const [qr, setQr] = useState<string | null>(null);
  const [qrTime, setQrTime] = useState<number | null>(null);
  const [qrAge, setQrAge] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState(false);
  const epoch = useRef(0);
  const statusFailure = useRef(false);
  const qrRef = useRef<string | null>(null);
  const qrRequest = useRef(0);
  const qrLoading = useRef(false);
  const saveAttempt = useRef<{ signature: string; key: string } | null>(null);
  const restartAttempt = useRef<string | null>(null);
  const connector = connectors.find((c) => c.id === id);
  const uncertain =
    !!connector?.stale ||
    statusFetchFailed ||
    pairingFetchFailed ||
    (api.capabilities.pairing && !pairing);
  const connected =
    !!connector?.enabled &&
    !uncertain &&
    (api.capabilities.pairing
      ? !!pairing?.connected
      : !!connector?.live_connected);
  const presentation = connectionState({
    enabled: !!connector?.enabled,
    uncertain,
    connected,
    state: pairing?.state ?? connector?.state,
  });
  const pending = pendingIssues(issues);
  const recovered = pending.filter((issue) => !!issue.recovered_at);
  const reviewIds = recovered.slice(0, 100).map((issue) => issue.id);
  const reviewConfirmed =
    reviewSnapshot.length > 0 &&
    reviewSnapshot.every((value) => reviewIds.includes(value)) &&
    reviewSnapshot.length === reviewIds.length;
  const dirty = !!selection && !sameSelection(picked, selection.selected);
  const clearQr = useCallback(() => {
    qrRequest.current++;
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
        setPairing(null);
        clearQr();
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
      setIssuesLoaded(false);
      setNextOffset(null);
      saveAttempt.current = null;
      restartAttempt.current = null;
      setReviewSnapshot([]);
      clearQr();
      return;
    }
    if (!current) return;
    if (!list.find((item) => item.id === current)?.enabled) clearQr();
    if (api.capabilities.pairing) {
      try {
        const p = await api.pairing(current);
        if (stamp !== epoch.current) return;
        setPairing(p);
        setPairingFetchFailed(false);
        if (["SCAN_QR_CODE", "WORKING"].includes(p.state))
          restartAttempt.current = null;
        if (!p.qr_available || list.find((item) => item.id === current)?.stale)
          clearQr();
      } catch (e) {
        if (stamp === epoch.current) {
          setPairing(null);
          setPairingFetchFailed(true);
          clearQr();
          report(e);
        }
      }
    }
    try {
      const records = await api.issues(current);
      if (stamp === epoch.current) {
        setIssues(records);
        setIssuesFetchFailed(false);
        setIssuesLoaded(true);
      }
    } catch (error) {
      if (stamp === epoch.current) setIssuesFetchFailed(true);
      throw error;
    }
  }, [api, id, clearQr, report]);

  const loadQr = useCallback(async () => {
    if (qrLoading.current) return;
    qrLoading.current = true;
    const stamp = epoch.current;
    const request = ++qrRequest.current;
    try {
      const blob = await api.qr(id);
      if (stamp !== epoch.current || request !== qrRequest.current) return;
      clearQr();
      const url = URL.createObjectURL(blob);
      qrRef.current = url;
      setQr(url);
      setQrTime(Date.now());
      setQrAge(0);
      setNotice("");
      setFailure(false);
    } catch (error) {
      if (stamp === epoch.current && request === qrRequest.current) {
        clearQr();
        throw error;
      }
    } finally {
      qrLoading.current = false;
    }
  }, [api, id, clearQr]);

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

  useEffect(() => {
    if (
      demo ||
      !pairing?.qr_available ||
      statusFetchFailed ||
      connector?.stale ||
      pairingFetchFailed ||
      !connector?.enabled
    )
      return;
    const update = () => {
      if (!document.hidden) void loadQr().catch(report);
    };
    update();
    const timer = setInterval(update, 20000);
    document.addEventListener("visibilitychange", update);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
    };
  }, [
    demo,
    pairing?.qr_available,
    statusFetchFailed,
    connector?.stale,
    pairingFetchFailed,
    connector?.enabled,
    loadQr,
    report,
  ]);

  useEffect(() => {
    if (qrTime === null) return;
    const timer = setTimeout(
      clearQr,
      Math.max(0, 30000 - (Date.now() - qrTime)),
    );
    return () => clearTimeout(timer);
  }, [qrTime, clearQr]);

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
  async function reconnect() {
    clearQr();
    restartAttempt.current ??= crypto.randomUUID();
    await api.restart(id, restartAttempt.current);
    restartAttempt.current = null;
    await refreshStatus();
    setNotice(
      demo
        ? "模拟重连完成。真实模式将自动显示新二维码。"
        : "已请求重连。二维码准备好后会自动显示，请稍候。",
    );
  }
  async function clearRecovered() {
    const count = await api.reviewIssues(id, reviewSnapshot);
    setReviewSnapshot([]);
    await refreshStatus();
    setNotice(
      `已清除 ${count} 项已恢复故障的待核对标记；历史记录保留，未恢复故障仍需处理。`,
    );
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
            : api.capabilities.pairing
              ? "在此窗口扫描本机二维码；会话选择与保存授权仍待接入。"
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
              setIssuesLoaded(false);
              setReviewSnapshot([]);
              restartAttempt.current = null;
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
            <section
              className={`panel pairing-panel connection-${presentation.tone}`}
            >
              <div className="section-heading">
                <h2 aria-live="polite">{presentation.title}</h2>
                <span className={`status-dot ${connected ? "online" : ""}`}>
                  {uncertain
                    ? "状态待确认"
                    : pairing
                      ? (states[pairing.state] ?? "状态未知")
                      : states[connector.state]}
                </span>
              </div>
              <p className="connection-guidance">{presentation.help}</p>
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
                    <p>
                      {api.capabilities.selection
                        ? "无需再次扫码，可选择工作会话。"
                        : "无需再次扫码；会话选择仍待接入。"}
                    </p>
                  </>
                ) : qr && !uncertain && connector.enabled ? (
                  <>
                    <img
                      src={qr}
                      alt="使用手机 WhatsApp 关联设备扫描此二维码"
                      onError={() => {
                        clearQr();
                        report(
                          new ConnectionError(
                            "WAHA_INVALID_QR",
                            "二维码显示失败，请刷新重试。",
                          ),
                        );
                      }}
                    />
                    <small>获取于 {qrAge} 秒前 · 自动更新中</small>
                  </>
                ) : (
                  <>
                    <div className="scan-mark" aria-hidden="true">
                      ⌗
                    </div>
                    <strong>
                      {uncertain
                        ? "请先确认连接状态"
                        : presentation.action === "restart"
                          ? "连接已断开，需要重新连接"
                          : demo
                            ? "扫码界面预览"
                            : "等待获取二维码"}
                    </strong>
                    <p>
                      {uncertain
                        ? "刷新状态后再获取二维码，避免使用旧的扫码信息。"
                        : presentation.action === "restart"
                          ? "点击下方「重新连接并获取二维码」，无需运行命令。"
                          : demo
                            ? "此区域展示真实二维码的位置"
                            : pairing?.qr_available
                              ? "正在加载本机二维码，也可点击「获取二维码」重试"
                              : "等待本机服务准备扫码，请刷新状态"}
                    </p>
                  </>
                )}
              </div>
              {api.capabilities.pairing && presentation.action === "qr" && (
                <ol className="scan-guide">
                  <li>手机打开 WhatsApp → 关联设备</li>
                  <li>选择「关联设备」，扫描这里的二维码</li>
                </ol>
              )}
              <div className="connection-actions">
                {presentation.action === "restart" && (
                  <button
                    disabled={busy || !api.capabilities.recovery}
                    onClick={() => void act(reconnect)}
                  >
                    {busy ? "正在重连…" : "重新连接并获取二维码"}
                  </button>
                )}
                {presentation.action === "qr" && (
                  <button
                    disabled={busy || !api.capabilities.pairing || demo}
                    onClick={() => void act(loadQr)}
                  >
                    {qr ? "刷新二维码" : "获取二维码"}
                  </button>
                )}
                <button
                  className={
                    presentation.action === "refresh" ? "" : "secondary"
                  }
                  disabled={busy}
                  onClick={() => void act(refreshStatus)}
                >
                  刷新状态
                </button>
              </div>
              {presentation.action === "restart" &&
                !api.capabilities.recovery && (
                  <p className="subtle">
                    一键重连需要已启用的本机开发服务及有效登录；正式接入接口待提供。
                  </p>
                )}
            </section>
            <section className="panel health-panel">
              <h2>连接与处理状态</h2>
              <dl>
                <div>
                  <dt>WhatsApp 会话</dt>
                  <dd>{connected ? "已连接" : "未连接或待确认"}</dd>
                </div>
                <div>
                  <dt>处理链路</dt>
                  <dd>
                    {uncertain
                      ? "待重新确认"
                      : connector.pipeline_ready
                        ? "采样就绪"
                        : "尚未就绪"}
                  </dd>
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
                    {issuesFetchFailed
                      ? "查询失败，需刷新"
                      : !issuesLoaded
                        ? "正在查询"
                        : `${pending.length} 项待核对`}
                  </dd>
                </div>
              </dl>
              {[false, true].map((restored) => {
                const group = pending.filter(
                  (issue) => !!issue.recovered_at === restored,
                );
                return (
                  group.length > 0 && (
                    <details className="issue-note" key={String(restored)}>
                      <summary>
                        {restored ? "已恢复，等待核对" : "尚未恢复，暂不能清除"}{" "}
                        · {group.length} 项
                      </summary>
                      {group.map((issue) => (
                        <div className="issue-entry" key={issue.id}>
                          <strong>
                            {issueLabels[issue.code] ?? issue.code}
                          </strong>
                          <small>
                            开始：
                            {new Date(issue.started_at).toLocaleString(
                              "zh-CN",
                              { timeZone: "Asia/Hong_Kong", hour12: false },
                            )}
                          </small>
                          {issue.recovered_at && (
                            <small>
                              恢复：
                              {new Date(issue.recovered_at).toLocaleString(
                                "zh-CN",
                                { timeZone: "Asia/Hong_Kong", hour12: false },
                              )}
                            </small>
                          )}
                        </div>
                      ))}
                    </details>
                  )
                );
              })}
              <div className="issue-review">
                <label>
                  <input
                    type="checkbox"
                    checked={reviewConfirmed}
                    disabled={
                      busy ||
                      issuesFetchFailed ||
                      !reviewIds.length ||
                      !api.capabilities.recovery
                    }
                    onChange={(event) =>
                      setReviewSnapshot(event.target.checked ? reviewIds : [])
                    }
                  />
                  <span>我已核对上述已恢复时段，确认无需导入历史消息。</span>
                </label>
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    issuesFetchFailed ||
                    !reviewConfirmed ||
                    !api.capabilities.recovery
                  }
                  onClick={() => void act(clearRecovered)}
                >
                  清除已恢复故障（{reviewIds.length}）
                </button>
                <p className="subtle">
                  仅清除已核对项的待处理标记，保留历史记录。未恢复故障不能清除；不会补拉或删除消息。
                  {recovered.length > 100 ? "每次最多核对 100 项。" : ""}
                </p>
                {!api.capabilities.recovery && (
                  <p className="subtle">
                    本机核对操作未启用；正式接入接口待提供。
                  </p>
                )}
              </div>
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
