import { useState } from "react";
import type { LoopApi, LoopIntent } from "./business-loop-api";
export function LoopCommand({
  api,
  intent,
  label,
  onDone,
  onError,
  onBusy,
  disabled = false,
  expiresAt = Infinity,
}: {
  api: LoopApi;
  intent: LoopIntent;
  label: string;
  onDone: () => void;
  onError: (e: unknown) => void;
  onBusy?: (v: boolean) => void;
  disabled?: boolean;
  expiresAt?: number;
}) {
  const [review, setReview] = useState<string | null>(null),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false);
  const binding = JSON.stringify(intent),
    current = review === binding;
  async function submit(retry = false) {
    if (
      Date.now() > expiresAt ||
      disabled ||
      busy ||
      !consent ||
      (retry ? review !== JSON.stringify(api.pending?.intent) : !current)
    )
      return;
    setBusy(true);
    onBusy?.(true);
    try {
      if (retry) await api.retry();
      else await api.submit(intent);
      setReview(null);
      setConsent(false);
      onDone();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
      onBusy?.(false);
    }
  }
  return (
    <div className="command-action">
      <button
        className="secondary"
        disabled={disabled || busy || !!api.pending || !!api.error}
        onClick={() => {
          setReview(binding);
          setConsent(false);
        }}
      >
        {label}
      </button>
      {current && (
        <div className="review-sheet" role="region" aria-label="操作复核">
          <h3>核对后保存</h3>
          <p>{intent.review}</p>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={busy}
            />
            我已核对内容、来源及当前版本，确认本次操作。
          </label>
          <button
            disabled={disabled || !consent || busy}
            onClick={() => void submit()}
          >
            确认保存
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setReview(null)}
          >
            返回修改
          </button>
        </div>
      )}
      {api.pending?.intent.path === intent.path && (
        <div className="notice stale">
          <strong>有一笔原操作等待核对</strong>
          <p>{api.pending.intent.review}</p>
          <p>
            编号 {api.pending.key}。不会自动重发；先读取当前数据，再核对原内容。
          </p>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={consent && review === JSON.stringify(api.pending.intent)}
              onChange={(e) => {
                setReview(JSON.stringify(api.pending!.intent));
                setConsent(e.target.checked);
              }}
            />
            我已核对原操作，按原编号查询／重试
          </label>
          <button
            disabled={
              disabled ||
              busy ||
              !consent ||
              review !== JSON.stringify(api.pending.intent)
            }
            onClick={() => void submit(true)}
          >
            核对原编号
          </button>
        </div>
      )}
      {api.error && <p role="alert">{api.error}</p>}
    </div>
  );
}
