import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  sendingApi,
  sendingMime,
  type SendAction,
  type SendDraft,
  type SendPayload,
  type SendPermission,
  type SendPolicy,
  type SendUpload,
} from "./waha-send-api";
import type { TimelineMessage } from "./waha-sync-api";

const names: Record<SendPayload["kind"], string> = {
  text: "文字 / 链接",
  image: "图片",
  file: "文件",
  audio: "普通音频附件",
  voice: "语音消息（Ogg/Opus）",
  video: "视频（MP4）",
  sticker: "贴纸（WebP）",
  location: "位置",
  contact: "联系人",
  poll: "投票",
  reaction: "表情回应",
};
const states: Record<string, string> = {
  draft: "待核对草稿",
  queued: "已批准，排队中",
  preparing: "连接检查中",
  dispatching: "提交中，不能取消",
  accepted: "WAHA 已接受",
  failed: "未提交成功",
  cancelled: "已取消",
  result_unknown: "结果未知，禁止重发",
  not_submitted: "尚未提交",
  sent: "已发送",
  delivered: "已送达",
  read: "已读",
  unknown: "未知",
};

export function WahaSend({
  connection,
  csrf,
  chat,
  label,
  enabled,
  messages,
  onSessionExpired,
}: {
  connection: string;
  csrf: string;
  chat: string;
  label: string;
  enabled: boolean;
  messages: TimelineMessage[];
  onSessionExpired?: () => void;
}) {
  const api = useMemo(() => sendingApi(connection, csrf), [connection, csrf]);
  const [installed, setInstalled] = useState(false),
    [permission, setPermission] = useState<SendPermission | null>(null);
  const [actions, setActions] = useState<SendAction[]>([]),
    [policies, setPolicies] = useState<SendPolicy[]>([]);
  const [cursor, setCursor] = useState<string | null>(null),
    [policyCursor, setPolicyCursor] = useState<string | null>(null);
  const [kind, setKind] = useState<SendPayload["kind"]>("text"),
    [mode, setMode] = useState<"manual" | "agent_assisted">("manual");
  const [text, setText] = useState(""),
    [caption, setCaption] = useState(""),
    [title, setTitle] = useState("");
  const [latitude, setLatitude] = useState(""),
    [longitude, setLongitude] = useState(""),
    [contactName, setContactName] = useState(""),
    [phone, setPhone] = useState("");
  const [options, setOptions] = useState(""),
    [multiple, setMultiple] = useState(false),
    [reaction, setReaction] = useState("👍"),
    [target, setTarget] = useState("");
  const [reply, setReply] = useState(""),
    [upload, setUpload] = useState<SendUpload | null>(null),
    [mime, setMime] = useState("");
  const [preview, setPreview] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [consent, setConsent] = useState(false),
    [policyConsent, setPolicyConsent] = useState(false);
  const [draftView, setDraftView] = useState<SendAction | null>(null),
    [uncertain, setUncertain] = useState(false);
  const [unknownNote, setUnknownNote] = useState(""),
    [unknownConsent, setUnknownConsent] = useState(false);
  const [recoverKey, setRecoverKey] = useState<string | null>(null);
  const storagePrefix = `gigmate-send-intent:${connection}:${chat}:`;
  function storedKey() {
    try {
      return (
        Object.keys(localStorage)
          .find(
            (k) =>
              k.startsWith(storagePrefix) &&
              /^[a-f0-9-]{36}$/i.test(k.slice(storagePrefix.length)),
          )
          ?.slice(storagePrefix.length) ?? null
      );
    } catch {
      return null;
    }
  }
  function clearReference(key: string) {
    try {
      localStorage.removeItem(storagePrefix + key);
    } catch {
      /* The server remains authoritative. */
    }
  }
  function updateRecovery() {
    const key = storedKey();
    setRecoverKey(key);
    setUncertain(!!key);
  }
  const scope = useRef(0),
    active = useRef(true),
    pending = useRef<{ key: string; command: SendDraft } | null>(null);
  const inFlight = useRef(false);
  const refreshSequence = useRef(0),
    selectedAction = useRef<string | null>(null),
    moreActions = useRef(false),
    morePolicies = useRef(false);
  selectedAction.current = draftView?.id ?? null;
  const permitted =
    !!permission?.enabled &&
    permission.chat_ids.includes(chat) &&
    !!permission.expires_at &&
    Date.parse(permission.expires_at) > Date.now();
  const report = useCallback(
    (error: unknown) => {
      const code =
        error && typeof error === "object" && "code" in error
          ? String(error.code)
          : error instanceof Error
            ? error.message
            : "SEND_FAILED";
      setNotice(code);
      if (code === "UNAUTHENTICATED") onSessionExpired?.();
    },
    [onSessionExpired],
  );
  const refresh = useCallback(async () => {
    const epoch = scope.current;
    const sequence = ++refreshSequence.current;
    const selected = selectedAction.current;
    try {
      const [caps, p, a, pol, chosen] = await Promise.all([
        api.capabilities(),
        api.permission(),
        api.actions(null, chat),
        api.policies(null, chat),
        selected ? api.action(selected) : Promise.resolve(null),
      ]);
      if (
        !active.current ||
        epoch !== scope.current ||
        sequence !== refreshSequence.current
      )
        return;
      setInstalled(caps.enabled);
      setPermission(p);
      setActions((old) =>
        moreActions.current
          ? [...new Map([...old, ...a.items].map((x) => [x.id, x])).values()]
          : a.items,
      );
      if (!moreActions.current) setCursor(a.next_cursor);
      setPolicies((old) =>
        morePolicies.current
          ? [...new Map([...old, ...pol.items].map((x) => [x.id, x])).values()]
          : pol.items,
      );
      if (!morePolicies.current) setPolicyCursor(pol.next_cursor);
      setDraftView((old) =>
        old
          ? chosen?.id === old.id
            ? chosen
            : (a.items.find((x) => x.id === old.id) ?? old)
          : null,
      );
    } catch (error) {
      if (
        active.current &&
        epoch === scope.current &&
        sequence === refreshSequence.current
      ) {
        setInstalled(false);
        setPermission(null);
        setPreview(null);
        report(error);
      }
    }
  }, [api, report, chat]);
  useEffect(() => {
    active.current = true;
    scope.current++;
    pending.current = null;
    updateRecovery();
    setDraftView(null);
    setUpload(null);
    setPreview(null);
    setText("");
    setCaption("");
    setReply("");
    setTarget("");
    setConsent(false);
    setPolicyConsent(false);
    setBusy(false);
    inFlight.current = false;
    setTitle("");
    setLatitude("");
    setLongitude("");
    setContactName("");
    setPhone("");
    setOptions("");
    setMultiple(false);
    setReaction("👍");
    setMime("");
    setMode("manual");
    setKind("text");
    setUnknownNote("");
    setUnknownConsent(false);
    setActions([]);
    setPolicies([]);
    moreActions.current = false;
    morePolicies.current = false;
    selectedAction.current = null;
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => {
      active.current = false;
      scope.current++;
      clearInterval(timer);
    };
  }, [refresh, chat]);
  useEffect(() => {
    setDraftView(null);
  }, [
    kind,
    mode,
    text,
    caption,
    title,
    latitude,
    longitude,
    contactName,
    phone,
    options,
    multiple,
    reaction,
    target,
    reply,
    upload?.id,
  ]);
  useEffect(() => {
    if (!enabled || !permitted) setPreview(null);
  }, [enabled, permitted]);
  useEffect(() => {
    if (!upload || !enabled || !permitted) return;
    let alive = true;
    let url: string | null = null;
    fetch(api.previewUrl(upload.id), {
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error("SEND_PREVIEW_UNAVAILABLE");
        return r.blob();
      })
      .then((blob) => {
        if (alive) {
          url = URL.createObjectURL(blob);
          setPreview(url);
        }
      })
      .catch((error) => {
        if (alive) {
          setPreview(null);
          report(error);
        }
      });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [upload, enabled, permitted, api, report]);
  async function run(work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    const epoch = scope.current;
    refreshSequence.current++;
    setBusy(true);
    setNotice("");
    try {
      await work();
    } catch (error) {
      if (active.current && epoch === scope.current) report(error);
    } finally {
      if (active.current && epoch === scope.current) {
        inFlight.current = false;
        setBusy(false);
        void refresh();
      }
    }
  }
  function payload(): SendPayload {
    const quote =
      reply && kind !== "reaction" ? { reply_snapshot_id: reply } : {};
    if (kind === "text") return { kind, text, ...quote };
    if (
      ["image", "file", "audio", "voice", "video", "sticker"].includes(kind)
    ) {
      if (!upload) throw new Error("请先上传并核对附件");
      return {
        kind,
        upload_id: upload.id,
        ...(["image", "file", "audio", "video"].includes(kind)
          ? { caption }
          : {}),
        ...quote,
      };
    }
    if (kind === "location") {
      if (!latitude.trim() || !longitude.trim()) throw new Error("请填写坐标");
      return {
        kind,
        latitude: Number(latitude),
        longitude: Number(longitude),
        title,
        ...quote,
      };
    }
    if (kind === "contact")
      return { kind, contacts: [{ name: contactName, phone }], ...quote };
    if (kind === "poll")
      return {
        kind,
        title,
        options: options
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
        multiple_answers: multiple,
        ...quote,
      };
    return { kind, target_snapshot_id: target, reaction };
  }
  async function prepare(policy?: SendPolicy) {
    if (pending.current && !uncertain) throw new Error("请先核对原请求");
    const epoch = scope.current;
    const restored = recoverKey ?? storedKey();
    if (restored && !pending.current) {
      const result = await api.request(restored);
      if (!active.current || epoch !== scope.current) return;
      clearReference(restored);
      updateRecovery();
      setDraftView(result.action);
      setNotice("已核对原请求，没有重新提交。");
      return;
    }
    if (!pending.current) {
      const [context, p] = await Promise.all([
        api.context(chat),
        api.permission(),
      ]);
      if (!active.current || epoch !== scope.current) return;
      const other = storedKey();
      if (other) {
        setRecoverKey(other);
        setUncertain(true);
        setNotice("本会话有待核对请求，请先核对原记录。");
        return;
      }
      pending.current = {
        key: crypto.randomUUID(),
        command: {
          expected_control_version: context.control_version,
          expected_permission_version: p.version,
          chat_id: chat,
          expected_context_version: context.context_version,
          mode: policy ? "agent_auto" : mode,
          payload: policy ? policy.payload : payload(),
          ...(policy ? { policy_id: policy.id } : {}),
          ...(policy?.work_order_id
            ? {
                work_order_id: policy.work_order_id,
                expected_work_order_version: policy.work_order_version,
              }
            : {}),
        },
      };
    }
    const frozen = pending.current;
    try {
      try {
        localStorage.setItem(storagePrefix + frozen.key, "pending");
      } catch {
        if (frozen.command.mode === "agent_auto")
          throw new Error("SEND_REQUEST_TRACKING_UNAVAILABLE");
      }
      const result = await api.draft(frozen.command, frozen.key);
      if (!active.current || epoch !== scope.current) return;
      pending.current = null;
      clearReference(frozen.key);
      updateRecovery();
      setDraftView(result);
      setNotice(
        policy
          ? "已按批准的固定内容政策排队。"
          : "草稿已保存，请核对下方最终内容再批准发送。",
      );
    } catch (error) {
      if (!active.current || epoch !== scope.current) return;
      const code =
        error && typeof error === "object" && "code" in error
          ? String(error.code)
          : "";
      if (code === "SEND_REQUEST_UNKNOWN") {
        setUncertain(true);
        setRecoverKey(frozen.key);
      } else {
        pending.current = null;
        clearReference(frozen.key);
        updateRecovery();
      }
      throw error;
    }
  }
  async function mutate(
    action: SendAction,
    operation: "approve" | "cancel" | "reconcile",
  ) {
    const epoch = scope.current;
    const result = await api.mutate(action, operation);
    if (active.current && epoch === scope.current) setDraftView(result);
  }
  if (!chat) return null;
  return (
    <section className="send-panel" aria-label="WhatsApp 发送">
      <h3>向「{label}」发送 WhatsApp 消息</h3>
      <p>
        读取聊天授权与发送授权分开。草稿、已批准、已接受和已送达是不同状态。
      </p>
      {!installed && <p>发送功能暂不可用，请联系接入负责人确认服务配置。</p>}
      {notice && <p role="status">{notice}</p>}
      <button
        className="secondary"
        disabled={busy}
        onClick={() => {
          moreActions.current = false;
          morePolicies.current = false;
          void refresh();
        }}
      >
        刷新发送记录
      </button>
      <label>
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        我允许本会话发送消息，授权有效期 24 小时
      </label>
      <button
        disabled={busy || !installed || !enabled || !consent}
        onClick={() =>
          void run(async () => {
            const p = await api.permission();
            await api.setPermission({
              expected_version: p.version,
              enabled: true,
              chat_ids: [...new Set([...p.chat_ids, chat])],
              expires_at: new Date(Date.now() + 86400000).toISOString(),
            });
            setConsent(false);
          })
        }
      >
        保存发送授权
      </button>
      <button
        className="secondary"
        disabled={busy || !permission?.enabled}
        onClick={() =>
          void run(async () => {
            const p = await api.permission();
            await api.setPermission({
              expected_version: p.version,
              enabled: false,
              chat_ids: [],
            });
            setPreview(null);
          })
        }
      >
        撤销全部发送授权
      </button>
      <fieldset
        disabled={busy || !installed || !enabled || !permitted || uncertain}
      >
        <legend>准备消息（尚未发送）</legend>
        <label>
          内容来源
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
          >
            <option value="manual">用户手动输入</option>
            <option value="agent_assisted">Agent 建议稿，人工核对</option>
          </select>
        </label>
        {mode === "agent_assisted" && (
          <p>自动润色暂不可用。可粘贴建议稿，修改并核对后发送。</p>
        )}
        <label>
          消息类型
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as typeof kind);
              setUpload(null);
              setPreview(null);
              setDraftView(null);
            }}
          >
            {Object.entries(names).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        {kind === "text" && (
          <label>
            文字
            <textarea
              value={text}
              maxLength={4096}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
        )}
        {["image", "file", "audio", "voice", "video", "sticker"].includes(
          kind,
        ) && (
          <>
            <label>
              文件类型（高级选项，可留空自动识别）
              <input
                value={mime}
                onChange={(e) => setMime(e.target.value)}
                placeholder="application/pdf"
              />
            </label>
            <input
              type="file"
              aria-label="上传发送附件"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file)
                  void run(async () => {
                    const epoch = scope.current;
                    if (file.size > 20 * 1024 * 1024)
                      throw new Error("附件最大 20 MiB");
                    const value = await api.upload(
                      file,
                      sendingMime(file, mime),
                    );
                    if (active.current && epoch === scope.current) {
                      setUpload(value);
                      setPreview(null);
                    }
                  });
                e.target.value = "";
              }}
            />
            {upload && (
              <p>
                {upload.filename} · {upload.size_bytes} 字节 · SHA256{" "}
                {upload.sha256.slice(0, 12)}
              </p>
            )}
            {preview && upload?.mimetype.startsWith("image/") && (
              <img className="send-preview" src={preview} alt="待发送图片" />
            )}
            {preview && upload?.mimetype.startsWith("audio/") && (
              <audio controls src={preview} />
            )}
            {preview && upload?.mimetype.startsWith("video/") && (
              <video className="send-preview" controls src={preview} />
            )}
            {preview && (
              <a
                href={preview}
                target="_blank"
                rel="noreferrer"
                download={upload?.filename}
              >
                查看 / 下载待发送文件
              </a>
            )}
            {["image", "file", "audio", "video"].includes(kind) && (
              <label>
                说明文字
                <textarea
                  value={caption}
                  maxLength={1024}
                  onChange={(e) => setCaption(e.target.value)}
                />
              </label>
            )}
          </>
        )}
        {kind === "location" && (
          <>
            <label>
              纬度
              <input
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
              />
            </label>
            <label>
              经度
              <input
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
              />
            </label>
            <label>
              地点名称
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
          </>
        )}
        {kind === "contact" && (
          <>
            <label>
              联系人姓名
              <input
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
              />
            </label>
            <label>
              电话号码（含 + 国家码）
              <input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </label>
          </>
        )}
        {kind === "poll" && (
          <>
            <label>
              投票问题
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              选项（每行一个，2–12 项）
              <textarea
                value={options}
                onChange={(e) => setOptions(e.target.value)}
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={multiple}
                onChange={(e) => setMultiple(e.target.checked)}
              />
              允许多选
            </label>
          </>
        )}
        <label>
          {kind === "reaction"
            ? "回应目标消息"
            : "引用回复（可选，先载入时间线）"}
          <select
            value={kind === "reaction" ? target : reply}
            onChange={(e) =>
              kind === "reaction"
                ? setTarget(e.target.value)
                : setReply(e.target.value)
            }
          >
            <option value="">请选择</option>
            {messages
              .filter((m) => !m.revoked)
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.text?.slice(0, 50) ?? m.kind} · {m.id.slice(-8)}
                </option>
              ))}
          </select>
        </label>
        {kind === "reaction" && (
          <label>
            表情（留空移除）
            <input
              value={reaction}
              maxLength={32}
              onChange={(e) => setReaction(e.target.value)}
            />
          </label>
        )}
        <button onClick={() => void run(() => prepare())}>
          保存待审核草稿
        </button>
        <label>
          <input
            type="checkbox"
            checked={policyConsent}
            onChange={(e) => setPolicyConsent(e.target.checked)}
          />
          预先允许 Agent 在本会话使用下方相同内容，24 小时内最多 5
          次；正文和附件不能改变
        </label>
        <button
          className="secondary"
          disabled={!policyConsent}
          onClick={() =>
            void run(async () => {
              const [context, p] = await Promise.all([
                api.context(chat),
                api.permission(),
              ]);
              await api.createPolicy({
                expected_control_version: context.control_version,
                expected_permission_version: p.version,
                chat_id: chat,
                payload: payload(),
                expires_at: new Date(Date.now() + 86400000).toISOString(),
                maximum_uses: 5,
              });
              setPolicyConsent(false);
              setNotice("固定内容政策已保存，尚未发送消息。");
            })
          }
        >
          批准固定内容自动政策
        </button>
      </fieldset>
      {uncertain && (
        <p>
          草稿保存结果待确认。
          <button disabled={busy} onClick={() => void run(() => prepare())}>
            核对原草稿请求
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const key = pending.current?.key ?? recoverKey;
                if (!key) return;
                const epoch = scope.current;
                const result = await api.cancelRequest(key);
                if (!active.current || epoch !== scope.current) return;
                clearReference(key);
                pending.current = null;
                updateRecovery();
                setDraftView(result.action);
                setNotice(
                  result.action &&
                    ["dispatching", "accepted", "result_unknown"].includes(
                      result.action.state,
                    )
                    ? "原任务已进入发送，无法取消；请核对下方记录，不要重发。"
                    : "原请求已取消；晚到的相同请求也不会创建发送任务。",
                );
              })
            }
          >
            取消原请求并核对
          </button>
        </p>
      )}
      {draftView && (
        <article className="send-review">
          <h4>最终发送快照 · {states[draftView.state]}</h4>
          <p>
            接收会话：{label} · 上下文版本 {draftView.context_version}
          </p>
          <pre>{JSON.stringify(draftView.payload, null, 2)}</pre>
          {Object.keys(draftView.work_order_versions ?? {}).length > 0 && (
            <p>
              关联工单版本（不自动确认业务）：
              {JSON.stringify(draftView.work_order_versions)}
              {draftView.work_order_id &&
                ` · 本条明确关联 ${draftView.work_order_id}`}
            </p>
          )}
          {draftView.upload && (
            <p>
              附件：{draftView.upload.filename} · {draftView.upload.size_bytes}{" "}
              字节 · SHA256 {draftView.upload.sha256}
              <br />
              <a
                href={api.previewUrl(draftView.upload.id)}
                target="_blank"
                rel="noreferrer"
              >
                核对这条草稿绑定的附件
              </a>
            </p>
          )}
          <p>
            截止 {new Date(draftView.expires_at).toLocaleString()} ·{" "}
            {states[draftView.delivery_status]}
          </p>
          {draftView.error_code && <p>{draftView.error_code}</p>}
          {draftView.state === "draft" && (
            <button
              disabled={busy || !enabled || !permitted}
              onClick={() => void run(() => mutate(draftView, "approve"))}
            >
              确认上述内容并发送
            </button>
          )}
          {["draft", "queued", "preparing"].includes(draftView.state) && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void run(() => mutate(draftView, "cancel"))}
            >
              取消此任务
            </button>
          )}
          {["result_unknown", "accepted"].includes(draftView.state) && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void run(() => mutate(draftView, "reconcile"))}
            >
              只读核对发送结果
            </button>
          )}
          {draftView.state === "result_unknown" &&
            !draftView.unknown_reviewed_at && (
              <div>
                <label>
                  人工核对说明
                  <input
                    value={unknownNote}
                    maxLength={500}
                    onChange={(e) => setUnknownNote(e.target.value)}
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={unknownConsent}
                    onChange={(e) => setUnknownConsent(e.target.checked)}
                  />
                  我已核对手机，理解本条可能已发出；保留未知状态，不重发本条，只允许后续独立任务继续
                </label>
                <button
                  disabled={busy || !unknownConsent || !unknownNote.trim()}
                  onClick={() =>
                    void run(async () => {
                      const epoch = scope.current;
                      const result = await api.reviewUnknown(
                        draftView,
                        unknownNote,
                      );
                      if (active.current && epoch === scope.current) {
                        setDraftView(result);
                        setUnknownConsent(false);
                        setUnknownNote("");
                      }
                    })
                  }
                >
                  记录核对并解除后续阻塞
                </button>
              </div>
            )}
          {draftView.unknown_reviewed_at && (
            <p>
              已记录当时未知状态的人工核对；当前状态以上方结果为准，本条不会重发。
            </p>
          )}
        </article>
      )}
      <h4>已批准的自动政策</h4>
      <p>
        自动触发尚未接入。目前只能由你明确触发已批准的固定内容；这不是 AI
        自由生成的自动回复。
      </p>
      {policies
        .filter((p) => p.chat_id === chat)
        .map((p) => (
          <article key={p.id}>
            <pre>{JSON.stringify(p.payload, null, 2)}</pre>
            <p>
              {p.enabled ? "有效" : "已撤销"} · 已预留 {p.uses}/{p.maximum_uses}{" "}
              次 · 截止 {new Date(p.expires_at).toLocaleString()}
            </p>
            <button
              disabled={
                busy ||
                uncertain ||
                !enabled ||
                !permitted ||
                !p.enabled ||
                p.uses >= p.maximum_uses ||
                Date.parse(p.expires_at) <= Date.now()
              }
              onClick={() => void run(() => prepare(p))}
            >
              按已授权政策提交
            </button>
            <button
              className="secondary"
              disabled={busy || !p.enabled}
              onClick={() =>
                void run(async () => {
                  await api.revokePolicy(p);
                })
              }
            >
              撤销此政策
            </button>
          </article>
        ))}
      {policyCursor && (
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const p = await api.policies(policyCursor, chat);
              morePolicies.current = true;
              setPolicies((old) => [...old, ...p.items]);
              setPolicyCursor(p.next_cursor);
            })
          }
        >
          加载更多政策
        </button>
      )}
      <h4>发送记录</h4>
      {actions
        .filter((a) => a.chat_id === chat)
        .map((a) => (
          <p key={a.id}>
            <button className="secondary" onClick={() => setDraftView(a)}>
              {names[a.payload.kind]} · {states[a.state]} ·{" "}
              {states[a.delivery_status]}
            </button>
          </p>
        ))}
      {cursor && (
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const p = await api.actions(cursor, chat);
              moreActions.current = true;
              setActions((old) => [...old, ...p.items]);
              setCursor(p.next_cursor);
            })
          }
        >
          加载更多发送记录
        </button>
      )}
      <p>
        结果未知时不会自动重发，同一会话后续发送暂停。没有 WAHA 返回的消息 ID
        时，无法自动证明某条相同文字就是本次发送；需人工核对。
      </p>
    </section>
  );
}
