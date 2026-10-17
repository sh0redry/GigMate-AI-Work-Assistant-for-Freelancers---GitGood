import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
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
        <div className="review-sheet" role="region" aria-label={t("操作复核")}>
          <h3>{t("核对后保存")}</h3>
          {/* Already formatted once; business values must never be parsed as UI templates. */}
          <p>{intent.review}</p>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={busy}
            />
            {t("我已核对内容、来源及当前版本，确认本次操作。")}
          </label>
          <button
            disabled={disabled || !consent || busy}
            onClick={() => void submit()}
          >
            {t("确认保存")}
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setReview(null)}
          >
            {t("返回修改")}
          </button>
        </div>
      )}
      {api.error && <p role="alert">{t(api.error)}</p>}
    </div>
  );
}

// A recovery entry remains available even after the successful operation removed
// its original form (for example an order was archived before the response died).
export function LoopRecovery({
  api,
  onDone,
  onError,
  onBusy,
}: {
  api: LoopApi;
  onDone: () => void;
  onError: (e: unknown) => void;
  onBusy: (v: boolean) => void;
}) {
  const [review, setReview] = useState(""),
    [busy, setBusy] = useState(false);
  const pending = api.pending,
    binding = JSON.stringify(pending);
  if (!pending) return null;
  async function retry() {
    if (busy || review !== binding) return;
    setBusy(true);
    onBusy(true);
    try {
      await api.retry();
      setReview("");
      onDone();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <div
      className="notice stale"
      role="region"
      aria-label={t("原业务操作核对")}
    >
      <h2>{t("有一笔原操作等待核对")}</h2>
      <p>{pending.intent.review}</p>
      <small>
        {t("原编号")}
        {pending.key}
      </small>
      <p>
        {t(
          "先用页面刷新读取当前状态，再核对原内容。不会自动重发，也不会换编号提交新操作；排期设置仅查询保存结果。",
        )}
      </p>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={review === binding}
          disabled={busy}
          onChange={(e) => setReview(e.target.checked ? binding : "")}
        />
        {t("我已读取当前状态并核对原操作，确认按原编号核查")}
      </label>
      <button
        disabled={busy || review !== binding}
        onClick={() => void retry()}
      >
        {t("核对原业务操作")}
      </button>
    </div>
  );
}
