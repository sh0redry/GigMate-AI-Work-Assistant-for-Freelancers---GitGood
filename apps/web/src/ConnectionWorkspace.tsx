import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { WahaMessages } from "./WahaMessages";
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
import {
  choiceExpired,
  connectionState,
  pendingIssues,
} from "./connection-state";

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
  WAHA_SETUP_VERSION_CONFLICT: "授权或连接已在其他窗口更新，请重新载入后核对。",
  CHAT_CHOICE_EXPIRED_OR_UNAVAILABLE:
    "聊天选项已过期，请重新发现会话后核对选择。",
  WAHA_OPERATION_NEEDS_RECONCILIATION:
    "连接操作结果未知，请明确核对；不要重复重连。",
  OPERATION_RESULT_UNKNOWN: "请求结果待确认，请刷新状态或使用原请求重试。",
  INVALID_RESPONSE: "服务响应未能完整读取，请刷新并核对状态。",
  CONNECTOR_PAUSED: "消息接收已暂停，可撤销已有授权；恢复后再发现新会话。",
  WAHA_DISCOVERY_REISSUE_REQUIRED:
    "上次会话发现未完成，核对后可重新发现最近会话。",
  WAHA_OPERATION_IN_PROGRESS: "已有操作正在处理，请刷新状态，暂勿重复提交。",
  OPERATION_PENDING: "操作仍在处理中，请刷新状态，暂勿重复提交。",
  WAHA_OPERATION_CANCELLED: "操作已取消，请刷新并核对后再决定下一步。",
  WAHA_OPERATION_FAILED: "操作未完成，请检查接入服务并核对状态。",
  WAHA_CONTROL_DISABLED: "接入后端未配置，请先准备本地接入服务。",
  WAHA_CONTROL_CONFIG_INVALID: "接入配置不匹配，请检查后端私有配置。",
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
  ...new Map([...a, ...b].map((c) => [c.id, c])).values(),
];
const sameSelection = (a: string[], b: Choice[]) =>
  a.length === b.length && b.every((c) => a.includes(c.id));
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
  onBusyChange,
}: {
  demo?: boolean;
  csrf?: string;
  onSessionExpired?: () => void;
  onBusyChange?: (busy: boolean) => void;
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
  const [selectionNeedsReload, setSelectionNeedsReload] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [choices, setChoices] = useState<Choice[]>([]);
  const [search, setSearch] = useState("");
  const [chatKind, setChatKind] = useState("all");
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
  const acting = useRef(false);
  const statusRequest = useRef(0);
  const connector = connectors.find((c) => c.id === id);
  const uncertain =
    !!connector?.stale ||
    statusFetchFailed ||
    pairingFetchFailed ||
    !!pairing?.provider_sample_stale ||
    !!pairing?.retry_available ||
    pairing?.operation_state === "result_unknown" ||
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
  const selectionStale =
    selectionNeedsReload ||
    (!!selection &&
      !!pairing &&
      selection.control_version !== pairing.control_version);
  const canDiscover =
    connected &&
    pairing?.available &&
    !pairing.operation_id &&
    !pairing.retry_available;
  const expiredPicked = choices.some(
    (choice) =>
      picked.includes(choice.id) &&
      !choice.selected &&
      choiceExpired(choice, clock),
  );
  const operationLabels = {
    connect: "连接",
    recover: "重连",
    inspect: "状态核对",
    discover: "会话发现",
  };
  const operationStates = {
    pending: "已排队",
    running: "正在处理",
    checking: "正在核对",
    succeeded: "已完成",
    failed: "失败",
    result_unknown: "结果未知",
    cancelled: "已取消",
  };
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

  const refreshStatus = useCallback(
    async (force = false) => {
      const stamp = epoch.current;
      const request = ++statusRequest.current;
      const currentRequest = () =>
        stamp === epoch.current && request === statusRequest.current;
      let list: Connector[];
      try {
        list = await api.connectors();
      } catch (e) {
        if (currentRequest()) {
          statusFailure.current = true;
          setStatusFetchFailed(true);
          setPairing(null);
          clearQr();
        }
        throw e;
      }
      if (!currentRequest()) return;
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
        setSelectionNeedsReload(false);
        setChoices([]);
        setPicked([]);
        setIssues([]);
        setIssuesLoaded(false);
        setNextOffset(null);
        setReviewSnapshot([]);
        clearQr();
        return;
      }
      if (!current) return;
      if (!list.find((item) => item.id === current)?.enabled) clearQr();
      if (api.capabilities.pairing) {
        try {
          const p = await api.pairing(current, force);
          if (!currentRequest()) return;
          setPairing(p);
          setPairingFetchFailed(false);
          if (
            !p.qr_available ||
            list.find((item) => item.id === current)?.stale
          )
            clearQr();
        } catch (e) {
          if (currentRequest()) {
            setPairing(null);
            setPairingFetchFailed(true);
            clearQr();
            report(e);
          }
        }
      }
      try {
        const records = await api.issues(current);
        if (currentRequest()) {
          setIssues(records);
          setIssuesFetchFailed(false);
          setIssuesLoaded(true);
        }
      } catch (error) {
        if (currentRequest()) setIssuesFetchFailed(true);
        throw error;
      }
    },
    [api, id, clearQr, report],
  );

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
        if (
          error instanceof ConnectionError &&
          error.code === "WAHA_NOT_WAITING_FOR_QR"
        ) {
          setPairing(await api.pairing(id, true));
          await refreshStatus();
          setNotice("扫码状态已变化，已重新核对连接。");
          return;
        }
        throw error;
      }
    } finally {
      qrLoading.current = false;
    }
  }, [api, id, clearQr, refreshStatus]);

  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);

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
    const timer = setInterval(() => {
      setClock(Date.now());
      setQrAge(qrTime ? Math.floor((Date.now() - qrTime) / 1000) : 0);
    }, 1000);
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
      const stamp = epoch.current;
      if (!document.hidden)
        void loadQr().catch((error) => {
          if (stamp === epoch.current) report(error);
        });
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
    if (acting.current) return;
    acting.current = true;
    const stamp = epoch.current;
    setBusy(true);
    setNotice("");
    setFailure(false);
    try {
      await task();
    } catch (e) {
      if (stamp === epoch.current) report(e);
    } finally {
      acting.current = false;
      if (stamp === epoch.current) setBusy(false);
    }
  }
  async function reconnect() {
    clearQr();
    try {
      await api.restart(id, crypto.randomUUID());
    } catch (error) {
      await refreshStatus().catch(() => {});
      throw error;
    }
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
    let value: Selection;
    try {
      value = await api.selection(id);
    } catch (error) {
      if (stamp === epoch.current) setSelectionNeedsReload(true);
      throw error;
    }
    if (stamp !== epoch.current) return;
    setSelection(value);
    setSelectionNeedsReload(false);
    setPicked(value.selected.map((c) => c.id));
    setChoices(value.choices);
    setNextOffset(null);
    setLoaded(false);
    await refreshStatus();
    setNotice(
      demo
        ? "已载入演示授权；取消勾选后保存即可模拟撤销。"
        : "已载入服务端授权；取消勾选后保存即可撤销。",
    );
  }
  async function discover() {
    const stamp = epoch.current;
    try {
      const discovery = await api.chats(id, 0);
      const value = await api.selection(id);
      if (stamp !== epoch.current) return;
      setSelection(value);
      setSelectionNeedsReload(false);
      setPicked(value.selected.map((c) => c.id));
      setChoices(mergeChoices(value.selected, discovery.items));
      setNextOffset(discovery.next_offset);
      setLoaded(true);
      setNotice(
        "已发现最近会话，请勾选并保存处理授权。每页最多读取 100 个会话，可加载更多；列表可能不完整。新选项按服务端原到期时间失效。",
      );
    } finally {
      await refreshStatus();
    }
  }
  async function save(next: string[]) {
    if (!selection || selectionStale) return;
    const stamp = epoch.current;
    const selected = next
      .map((key) => choices.find((c) => c.id === key))
      .filter((c): c is Choice => !!c);
    let value: Selection;
    try {
      value = await api.save(id, selection, selected, crypto.randomUUID());
    } catch (error) {
      if (stamp === epoch.current) setSelectionNeedsReload(true);
      throw error;
    }
    if (stamp !== epoch.current) return;
    setSelection(value);
    setSelectionNeedsReload(false);
    setPicked(value.selected.map((c) => c.id));
    setChoices(value.choices);
    await refreshStatus();
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
              ? "连接后载入聊天并明确保存处理授权；自动回复不会开启。"
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
              setSelectionNeedsReload(false);
              setChoices([]);
              setPicked([]);
              setIssues([]);
              setIssuesLoaded(false);
              setReviewSnapshot([]);
              setNextOffset(null);
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
                  {!connector.enabled
                    ? "接收已暂停"
                    : uncertain
                      ? "状态待确认"
                      : pairing
                        ? (states[pairing.state] ?? "状态未知")
                        : states[connector.state]}
                </span>
              </div>
              <p className="connection-guidance">{presentation.help}</p>
              {pairing && !pairing.available && (
                <p className="connection-notice error">
                  本机接入配置不可用，请联系接入负责人检查。仍可载入已有授权并撤销。
                </p>
              )}
              {pairing?.operation_state && (
                <p role="status">
                  最近
                  {pairing.operation_action
                    ? operationLabels[pairing.operation_action]
                    : "连接"}
                  操作：
                  {operationStates[pairing.operation_state] ??
                    pairing.operation_state}
                  {pairing.operation_error &&
                    ` · ${errors[pairing.operation_error] ?? "请核对服务后刷新。"}`}
                  {pairing.operation_error && (
                    <small>错误编号：{pairing.operation_error}</small>
                  )}
                </p>
              )}
              {pairing?.retry_available && (
                <p className="connection-notice error">
                  上次请求响应丢失，暂不创建新的连接操作。使用原请求核对会保留原版本和请求键。
                </p>
              )}
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
                        : "无需再次扫码，可载入并选择工作会话。"}
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
                      {!connector.enabled
                        ? "消息接收已暂停"
                        : uncertain
                          ? "请先确认连接状态"
                          : presentation.action === "restart"
                            ? "连接已断开，需要重新连接"
                            : demo
                              ? "扫码界面预览"
                              : "等待获取二维码"}
                    </strong>
                    <p>
                      {!connector.enabled
                        ? "恢复消息接收后再检查连接；暂停期间不显示二维码。"
                        : uncertain
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
                {!connected &&
                  connector.enabled &&
                  !pairing?.operation_id &&
                  pairing?.available &&
                  !pairing.retry_available &&
                  !["SCAN_QR_CODE", "STARTING"].includes(
                    pairing?.state ?? "",
                  ) &&
                  presentation.action !== "restart" && (
                    <button
                      disabled={busy || !api.capabilities.start}
                      onClick={() =>
                        void act(async () => {
                          try {
                            await api.start(id, crypto.randomUUID());
                          } finally {
                            await refreshStatus();
                          }
                        })
                      }
                    >
                      开始连接
                    </button>
                  )}
                {pairing?.operation_state === "result_unknown" && (
                  <button
                    disabled={busy || !api.capabilities.recovery}
                    onClick={() =>
                      void act(async () => {
                        await api.reconcile(id);
                        await refreshStatus();
                      })
                    }
                  >
                    核对未知操作（不重发）
                  </button>
                )}
                {pairing?.retry_available && (
                  <button
                    disabled={busy || !api.capabilities.start}
                    onClick={() =>
                      void act(async () => {
                        try {
                          const stamp = epoch.current;
                          const discovery = await api.retry(id);
                          if (discovery && stamp === epoch.current) {
                            if (!selection) {
                              const value = await api.selection(id);
                              if (stamp !== epoch.current) return;
                              setSelection(value);
                              setSelectionNeedsReload(false);
                              setPicked(value.selected.map((c) => c.id));
                            }
                            setChoices((c) => mergeChoices(c, discovery.items));
                            setNextOffset(discovery.next_offset);
                            setLoaded(true);
                          }
                        } finally {
                          await refreshStatus();
                        }
                      })
                    }
                  >
                    使用原请求核对
                  </button>
                )}
                <button
                  className="secondary"
                  disabled={busy || !api.capabilities.start}
                  onClick={() =>
                    void act(async () => {
                      clearQr();
                      if (connector.enabled) await api.pause(id);
                      else await api.resume(id);
                      await refreshStatus();
                    })
                  }
                >
                  {connector.enabled ? "暂停消息接收" : "恢复消息接收"}
                </button>
                {presentation.action === "restart" && (
                  <button
                    disabled={
                      busy ||
                      !!pairing?.operation_id ||
                      !pairing?.available ||
                      !!pairing.retry_available ||
                      !api.capabilities.recovery
                    }
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
                  onClick={() => void act(() => refreshStatus(true))}
                >
                  刷新状态
                </button>
              </div>
              {presentation.action === "restart" &&
                !api.capabilities.recovery && (
                  <p className="subtle">
                    一键重连需要有效登录和已配置的接入后端。
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
                  <p className="subtle">故障核对需要有效登录及明确确认。</p>
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
                disabled={busy || !api.capabilities.selection}
                onClick={() => void act(loadSelection)}
              >
                {selection
                  ? dirty
                    ? "放弃勾选并重新载入"
                    : "重新载入会话"
                  : "载入会话与授权"}
              </button>
              <button
                className="secondary"
                disabled={
                  busy || dirty || !canDiscover || !api.capabilities.selection
                }
                onClick={() => void act(discover)}
              >
                发现最近会话
              </button>
              {selection && (
                <small>
                  {demo ? "演示版本" : "服务端版本"} {selection.control_version}{" "}
                  · {selection.selected.length} 个已授权
                </small>
              )}
            </div>
            <p className="subtle">
              已有授权可在断线、暂停或接入配置不可用时读取及撤销。发现新会话需要有效连接；最多读取
              每页 100 个会话，可加载更多。
            </p>
            {selectionStale && (
              <p className="connection-notice error" role="alert">
                授权版本已变化、读取失败或保存结果待确认。请重新载入并核对后再保存；不会自动重试。
              </p>
            )}
            {expiredPicked && (
              <p className="connection-notice error" role="alert">
                勾选的新会话已过期。请放弃勾选并重新发现，再核对后保存。
              </p>
            )}
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
                    ? "先载入已有授权。连接后点击「发现最近会话」，勾选后明确保存。"
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
                        ? "可在手机创建测试聊天后重新发现最近会话。"
                        : !pairing?.available
                          ? "当前没有已授权会话。接入配置恢复后可发现新会话。"
                          : connected
                            ? "尚未发现会话，请点击「发现最近会话」。"
                            : "尚未连接；当前没有已授权会话。"}
                    </p>
                  </div>
                )}
                <div className="chat-choices">
                  <label>
                    搜索已载入聊天
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="聊天名称"
                    />
                  </label>
                  <label>
                    聊天类型
                    <select
                      value={chatKind}
                      onChange={(e) => setChatKind(e.target.value)}
                    >
                      <option value="all">全部</option>
                      <option value="direct">个人聊天</option>
                      <option value="group">群聊</option>
                      <option value="selected">已授权</option>
                    </select>
                  </label>
                  {choices
                    .filter(
                      (c) =>
                        c.label
                          .toLocaleLowerCase()
                          .includes(search.toLocaleLowerCase()) &&
                        (chatKind === "all" ||
                          (chatKind === "selected" && c.selected) ||
                          c.kind === chatKind),
                    )
                    .map((c, i) => (
                      <label className="chat-choice" key={c.id}>
                        <input
                          type="checkbox"
                          checked={picked.includes(c.id)}
                          disabled={
                            busy ||
                            (!picked.includes(c.id) &&
                              (picked.length >= 100 ||
                                (!c.selected &&
                                  (!canDiscover || choiceExpired(c, clock)))))
                          }
                          onChange={(e) => {
                            setPicked((p) =>
                              e.target.checked
                                ? [...p, c.id]
                                : p.filter((k) => k !== c.id),
                            );
                            setNotice("");
                          }}
                        />
                        <span className="chat-avatar" aria-hidden="true">
                          {c.label.slice(0, 1) || "聊"}
                        </span>
                        <span className="chat-title">
                          <strong>
                            {c.label === "已授权会话"
                              ? `已授权会话 ${i + 1}`
                              : c.label}
                          </strong>
                          <small>
                            {"聊天"} ·{" "}
                            {selection.selected.some((s) => s.id === c.id)
                              ? demo
                                ? "演示已授权"
                                : "服务端已授权"
                              : "尚未授权"}
                            {!c.selected && choiceExpired(c, clock)
                              ? " · 选项已过期"
                              : ""}
                          </small>
                        </span>
                      </label>
                    ))}
                </div>
                {nextOffset !== null && (
                  <button
                    className="secondary"
                    disabled={busy || !canDiscover}
                    onClick={() =>
                      void act(async () => {
                        const stamp = epoch.current;
                        const discovery = await api.chats(id, nextOffset);
                        if (stamp !== epoch.current) return;
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
                    disabled={
                      busy ||
                      !dirty ||
                      selectionStale ||
                      expiredPicked ||
                      statusFetchFailed
                    }
                    onClick={() => void act(() => save(picked))}
                  >
                    {busy ? "处理中…" : "保存会话授权"}
                  </button>
                  <button
                    className="secondary"
                    disabled={
                      busy || selectionStale || !selection.selected.length
                    }
                    onClick={() => void act(() => save([]))}
                  >
                    撤销全部授权
                  </button>
                  <button
                    className="secondary"
                    disabled={busy || !dirty}
                    onClick={() => {
                      setPicked(selection.selected.map((c) => c.id));
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
      {!demo && id && (
        <WahaMessages
          key={`${id}:${csrf}`}
          connection={id}
          csrf={csrf}
          enabled={!!connector?.enabled}
          issues={issues}
          onSessionExpired={onSessionExpired}
        />
      )}
    </section>
  );
}
