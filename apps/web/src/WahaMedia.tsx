import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { mediaApi, type Attachment, type MediaJob } from "./waha-media-api";
import { ConnectionError } from "./connection-api";

const states: Record<string, string> = {
  pending: "等待处理",
  running: "处理中",
  retry_wait: "等待重试",
  succeeded: "本次任务完成",
  failed: "失败",
  cancelled: "已取消",
  result_unknown: "模型结果待核对",
};
const stages: Record<string, string> = {
  download: "附件下载",
  processing: "B 提取与理解",
  reconciling: "只读核对模型结果",
};
const errors: Record<string, string> = {
  MEDIA_API_NOT_INSTALLED: "本机后端尚未升级媒体接口，请先按本批联调文档升级。",
  MEDIA_STORAGE_NOT_CONFIGURED: "本机尚未启用附件存储，请按媒体联调文档配置。",
  MEDIA_PROCESSOR_NOT_CONFIGURED:
    "B 的 OCR / 转写 / 解析 / GenAI 处理器尚未配置。原文件可先预览。",
  MEDIA_PROCESSOR_INVALID_RESULT:
    "B 返回的结构或来源不符合协议，需要修正处理器。",
  MEDIA_PROCESSING_RESULT_UNKNOWN:
    "模型可能已处理，请核对原任务，不自动重复调用。",
  MEDIA_JOB_ACTIVE_OR_UNKNOWN: "此附件已有任务，请先核对原任务。",
  MEDIA_SOURCE_CHANGED: "来源或上下文已变化，请重新载入核对。",
};

export function WahaMedia({
  connection,
  csrf,
  snapshot,
  mimetype,
  enabled,
  onSessionExpired,
}: {
  connection: string;
  csrf: string;
  snapshot: string;
  mimetype: string | null;
  enabled: boolean;
  onSessionExpired?: () => void;
}) {
  const api = useMemo(() => mediaApi(connection, csrf), [connection, csrf]);
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [caps, setCaps] = useState<Awaited<
    ReturnType<typeof api.capabilities>
  > | null>(null);
  const [asset, setAsset] = useState<Attachment | null>(null),
    [job, setJob] = useState<MediaJob | null>(null);
  const [downloadConsent, setDownloadConsent] = useState(false),
    [modelConsent, setModelConsent] = useState(false);
  const [timezone, setTimezone] = useState("");
  const [handoff, setHandoff] = useState<Awaited<
    ReturnType<typeof api.evidence>
  > | null>(null);
  const [url, setUrl] = useState<string | null>(null),
    [text, setText] = useState<string | null>(null),
    [note, setNote] = useState("");
  const epoch = useRef(0);
  const active = useRef(false),
    acting = useRef(false),
    previewRef = useRef<string | null>(null);
  const attempt = useRef<{
    key: string;
    value: Parameters<typeof api.start>[0];
  } | null>(null);
  const clearPreview = useCallback(() => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = null;
    setUrl(null);
    setText(null);
  }, []);
  const report = useCallback(
    (error: unknown) => {
      if (!active.current) return;
      clearPreview();
      setAsset(null);
      setHandoff(null);
      const code =
        error instanceof ConnectionError ? error.code : "MEDIA_UNAVAILABLE";
      setNotice(errors[code] ?? code);
      if (code === "UNAUTHENTICATED") onSessionExpired?.();
    },
    [clearPreview, onSessionExpired],
  );
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      epoch.current++;
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, []);
  useEffect(() => {
    epoch.current++;
    if (!open || !enabled) {
      clearPreview();
      setAsset(null);
      setHandoff(null);
    }
    return () => {
      epoch.current++;
    };
  }, [open, enabled, clearPreview]);
  const refresh = useCallback(async () => {
    const generation = epoch.current;
    const capabilities = await api.capabilities();
    if (!capabilities.enabled) {
      if (active.current && generation === epoch.current) {
        setCaps(capabilities);
        setAsset(null);
        clearPreview();
      }
      return;
    }
    const current = await api.find(snapshot);
    const savedJob = current?.latest_job_id
      ? await api.job(current.latest_job_id)
      : null;
    if (active.current && generation === epoch.current) {
      setCaps(capabilities);
      setAsset(current);
      setHandoff((previous) =>
        previous &&
        current?.reviewed_at &&
        previous.attachment_version === current.version &&
        previous.context_version === current.context_version &&
        previous.result_job_id === current.result_job_id &&
        previous.reviewed_at === current.reviewed_at
          ? previous
          : null,
      );
      if (savedJob) {
        setJob(savedJob);
        if (["succeeded", "failed", "cancelled"].includes(savedJob.state))
          attempt.current = null;
      }
      if (!current?.preview_available) clearPreview();
    }
  }, [api, snapshot, clearPreview]);
  useEffect(() => {
    if (!open || !enabled) {
      clearPreview();
      return;
    }
    let live = true,
      running = false;
    const tick = async () => {
      if (running) return;
      running = true;
      try {
        await refresh();
        if (job) {
          const current = await api.job(job.id);
          if (live && active.current) {
            setJob(current);
            if (["succeeded", "failed", "cancelled"].includes(current.state))
              attempt.current = null;
          }
        }
      } catch (error) {
        if (live) report(error);
      } finally {
        running = false;
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), 5000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [open, enabled, refresh, api, job?.id, clearPreview, report]);
  async function act(task: () => Promise<void>) {
    if (acting.current) return;
    acting.current = true;
    setBusy(true);
    setNotice("");
    try {
      await task();
    } catch (error) {
      report(error);
    } finally {
      acting.current = false;
      if (active.current) setBusy(false);
    }
  }
  async function start() {
    attempt.current ??= {
      key: crypto.randomUUID(),
      value: {
        snapshot_id: snapshot,
        consent_download: true,
        process: modelConsent,
        consent_model: modelConsent,
        timezone: timezone.trim() || null,
      },
    };
    let current: MediaJob;
    try {
      current = await api.start(attempt.current.value, attempt.current.key);
    } catch (error) {
      if (
        error instanceof ConnectionError &&
        error.code !== "MEDIA_REQUEST_UNKNOWN"
      )
        attempt.current = null;
      throw error;
    }
    if (active.current) {
      setJob(current);
      if (["succeeded", "failed", "cancelled"].includes(current.state))
        attempt.current = null;
    }
  }
  async function preview() {
    if (!asset) return;
    const generation = epoch.current;
    const blob = await api.preview(asset.id);
    if (!active.current || generation !== epoch.current) return;
    clearPreview();
    if (blob.type.startsWith("text/plain")) {
      const value = await blob.text();
      if (active.current && generation === epoch.current)
        setText(
          value.slice(0, 100000) +
            (value.length > 100000
              ? "\n\n[预览仅展示前 100000 字符，请下载原文件核对全文。]"
              : ""),
        );
    } else {
      const value = URL.createObjectURL(blob);
      previewRef.current = value;
      setUrl(value);
    }
  }
  const waiting =
    job &&
    ["pending", "running", "retry_wait", "result_unknown"].includes(job.state);
  return (
    <section className="media-panel">
      <button
        className="secondary"
        onClick={() => {
          setOpen(!open);
          if (open) clearPreview();
        }}
      >
        附件读取与核对{open ? " · 收起" : ""}
      </button>
      {open && (
        <>
          <p>
            只读取这条已授权附件，最大 20 MB。提取和模型建议不等于工单确认。
          </p>
          {notice && <p role="status">{notice}</p>}
          {caps && !caps.enabled && (
            <p>{errors.MEDIA_STORAGE_NOT_CONFIGURED}</p>
          )}
          {caps?.enabled && !caps.processor_configured && (
            <p>{errors.MEDIA_PROCESSOR_NOT_CONFIGURED}</p>
          )}
          {mimetype && caps && !caps.accepted_types.includes(mimetype) && (
            <p>本批不支持此文件类型。</p>
          )}
          <fieldset
            disabled={
              busy ||
              !!waiting ||
              !!attempt.current ||
              !enabled ||
              !caps?.enabled
            }
          >
            <label>
              本次解释日期的时区（可留空）
              <input
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder="例如 Asia/Hong_Kong"
                maxLength={100}
              />
            </label>
            <p>
              请填写适用的 IANA
              时区，不会根据手机号或电脑猜测；缺少时间依据时应交由人工核对。
            </p>
            <label>
              <input
                type="checkbox"
                checked={downloadConsent}
                onChange={(e) => setDownloadConsent(e.target.checked)}
              />
              同意下载此附件到本机私有存储并预览
            </label>
            <label>
              <input
                type="checkbox"
                disabled={!caps?.processor_configured}
                checked={modelConsent}
                onChange={(e) => setModelConsent(e.target.checked)}
              />
              另行同意将此附件交给 B 配置的提取与 GenAI 服务
            </label>
            <button
              disabled={
                !downloadConsent ||
                !mimetype ||
                !caps?.accepted_types.includes(mimetype)
              }
              onClick={() => void act(start)}
            >
              {attempt.current ? "使用原请求核对" : "读取附件"}
            </button>
          </fieldset>
          {attempt.current && !job && (
            <button disabled={busy} onClick={() => void act(start)}>
              使用原请求核对（保留原下载和模型同意选项）
            </button>
          )}
          {job && (
            <p>
              {stages[job.stage]} · {states[job.state]}
              {job.error_code &&
                ` · ${errors[job.error_code] ?? job.error_code}`}
            </p>
          )}
          {job && ["pending", "running", "retry_wait"].includes(job.state) && (
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const current = await api.cancel(job.id);
                  if (active.current) setJob(current);
                })
              }
            >
              取消此任务
            </button>
          )}
          {job?.state === "result_unknown" && (
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const current = await api.reconcile(job.id);
                  if (active.current) setJob(current);
                })
              }
            >
              只读核对模型结果（不重发）
            </button>
          )}
          {asset && (
            <>
              <p>
                原消息时间：{asset.input_context?.message_sent_at ?? "未知"} ·
                日期解释时区：
                {asset.input_context?.timezone ?? "未指定"}（商户本次选择）
              </p>
              {(!asset.input_context?.message_sent_at ||
                !asset.input_context?.timezone) && (
                <p>
                  日期依据不完整：“明天”等相对日期需要人工确认，观察时间不能代替发送时间。
                </p>
              )}
              <p>
                附件版本 {asset.version} · {asset.mimetype} ·{" "}
                {asset.size_bytes ?? 0} 字节 · 来源指纹{" "}
                {asset.source_fingerprint.slice(0, 12)}
              </p>
              {asset.preview_available && (
                <button disabled={busy} onClick={() => void act(preview)}>
                  预览原附件
                </button>
              )}
              {asset.preview_available && (
                <a href={api.downloadUrl(asset.id)} download>
                  下载原附件
                </a>
              )}
              {url && asset.mimetype?.startsWith("image/") && (
                <img className="media-preview" src={url} alt="已授权附件预览" />
              )}
              {url && asset.mimetype?.startsWith("audio/") && (
                <audio src={url} controls />
              )}
              {url && asset.mimetype === "application/pdf" && (
                <iframe
                  title="已授权 PDF 预览"
                  src={url}
                  sandbox=""
                  className="media-pdf"
                />
              )}
              {text !== null && <pre className="media-text">{text}</pre>}
              {asset.result && (
                <>
                  <h4>提取文字与来源</h4>
                  <p>
                    结果任务：{asset.result_job_id?.slice(-8)}
                    {asset.result_job_id !== asset.latest_job_id
                      ? " · 显示上次已完成的结果，请核对最近任务状态"
                      : ""}
                  </p>
                  <p>
                    提取范围：{asset.result.coverage ?? "unknown"} ·{" "}
                    {asset.result.provider} / {asset.result.model_version}
                  </p>
                  {asset.result.segments.map((s, i) => (
                    <div key={i} id={`media-${asset.id}-segment-${i}`}>
                      <small>
                        来源片段 {i + 1}
                        {s.page && ` · 第 ${s.page} 页`}
                        {s.start_ms !== null &&
                          ` · ${s.start_ms}–${s.end_ms} ms`}
                      </small>
                      <p>{s.text}</p>
                    </div>
                  ))}
                  <h4>GenAI 建议，尚未确认</h4>
                  <p>{asset.result.summary}</p>
                  {(asset.result.suggestions ?? []).map((s, i) => (
                    <p key={i}>
                      {s.field}：{s.text}（片段{" "}
                      {s.source_indices.map((x) => (
                        <a key={x} href={`#media-${asset.id}-segment-${x}`}>
                          片段 {x + 1}{" "}
                        </a>
                      ))}
                      ）
                    </p>
                  ))}
                  {(asset.result.unresolved_questions ?? []).map((q, i) => (
                    <p key={i}>待核对：{q}</p>
                  ))}
                  <label>
                    核对备注
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={2000}
                    />
                  </label>
                  <button
                    disabled={busy || !enabled}
                    onClick={() =>
                      void act(async () => {
                        const current = await api.review(asset, note);
                        if (active.current) setAsset(current);
                      })
                    }
                  >
                    标记已核对来源（不确认工单）
                  </button>
                  {asset.reviewed_at && (
                    <p>
                      来源已核对 ·{" "}
                      {new Date(asset.reviewed_at).toLocaleString()} ·{" "}
                      {asset.review_note}
                    </p>
                  )}
                  <button
                    disabled={busy || !enabled || !asset.reviewed_at}
                    onClick={() =>
                      void act(async () => {
                        const generation = epoch.current;
                        const value = await api.evidence(asset);
                        if (active.current && generation === epoch.current)
                          setHandoff(value);
                      })
                    }
                  >
                    查看业务交接资料（不写入工单）
                  </button>
                  {handoff &&
                    asset.reviewed_at &&
                    handoff.attachment_version === asset.version &&
                    handoff.context_version === asset.context_version &&
                    handoff.result_job_id === asset.result_job_id &&
                    handoff.reviewed_at === asset.reviewed_at && (
                      <div className="media-handoff">
                        <p>
                          来源已核对，业务仍需单独确认。C
                          使用这些来源标识前必须重新检查权限、版本和有效期。
                        </p>
                        <p>
                          附件 {handoff.attachment_id} · 上下文{" "}
                          {handoff.context_version} · 来源任务{" "}
                          {handoff.result_job_id}
                        </p>
                        <p>
                          有效期：{handoff.expires_at} · SHA-256：
                          {handoff.sha256}
                        </p>
                      </div>
                    )}
                </>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
