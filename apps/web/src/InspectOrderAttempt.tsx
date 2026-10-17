import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { useEffect } from "react";
import type { OrderCommands } from "./order-command-api";
import type { Order } from "./workspace-api";
import { orderStates } from "./work-order-view";

export function InspectOrderAttempt({
  commands,
  ready,
  busy,
  onBusy,
  onError,
  onDone,
}: {
  commands: OrderCommands;
  ready: boolean;
  busy: boolean;
  onBusy: (value: boolean) => void;
  onError: (error: unknown) => void;
  onDone: () => void;
}) {
  const [saved, setSaved] = useState<Order | null>(null);
  const [consent, setConsent] = useState(false);
  const key = commands.attempt?.key;
  useEffect(() => {
    setSaved(null);
    setConsent(false);
  }, [key]);
  return (
    <div className="change">
      <p>
        {t(
          "也可以只读核对服务端的原操作保存记录。此检查不会执行、重发或撤销操作；未找到记录时仍需保留原编号。",
        )}
      </p>
      <button
        className="secondary"
        disabled={!ready || busy || !!commands.error}
        onClick={() => {
          onBusy(true);
          setSaved(null);
          setConsent(false);
          void commands
            .inspect()
            .then(setSaved)
            .catch(onError)
            .finally(() => onBusy(false));
        }}
      >
        {t("只读核对已保存结果")}
      </button>
      {saved && (
        <>
          <p>
            {t("服务端已保存：「")}
            {saved.summary}
            {t("」 · 当时版本 v")}
            {saved.version} · {orderStates[saved.status]}
            {t("。结束后会刷新当前业务数据。")}
          </p>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={busy || !ready}
            />
            {t("我已核对保存结果，结束这条原记录；这不会撤销或重新执行操作。")}
          </label>
          <button
            disabled={!ready || busy || !consent || !!commands.error}
            onClick={() => {
              try {
                commands.retireInspected();
                setSaved(null);
                setConsent(false);
                onDone();
              } catch (e) {
                onError(e);
              }
            }}
          >
            {t("结束已核对的原记录")}
          </button>
        </>
      )}
    </div>
  );
}
