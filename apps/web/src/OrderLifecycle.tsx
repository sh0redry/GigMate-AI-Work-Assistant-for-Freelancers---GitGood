import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import type { Order } from "./workspace-api";
import type { OrderTarget, OrderCommands } from "./order-command-api";
import { orderStates } from "./work-order-view";
const transitions: Record<Order["status"], OrderTarget[]> = {
  unclassified: ["cancelled"],
  pending_confirmation: ["cancelled"],
  confirmed: ["in_progress", "waiting_customer", "completed", "cancelled"],
  in_progress: ["waiting_customer", "completed", "cancelled"],
  waiting_customer: ["in_progress", "completed", "cancelled"],
  completed: [],
  cancelled: [],
};
export function OrderLifecycle({
  order,
  enabled,
  ready,
  commands,
  onDone,
  onError,
  onBusyChange,
}: {
  order: Order;
  enabled: boolean;
  ready: boolean;
  commands: OrderCommands;
  onDone: () => void;
  onError: (e: unknown) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [target, setTarget] = useState<OrderTarget | null>(null),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false);
  const [binding, setBinding] = useState(0);
  const allowed = transitions[order.status],
    current = binding === order.version;
  async function submit() {
    if (
      !target ||
      !consent ||
      !enabled ||
      !ready ||
      !current ||
      busy ||
      !allowed.includes(target)
    )
      return;
    setBusy(true);
    onBusyChange(true);
    try {
      await commands.submit({
        kind: "status",
        orderId: order.id,
        body: {
          status: target,
          expected_version: order.version,
          acknowledge_open_items: false,
        },
      });
      setTarget(null);
      setConsent(false);
      onDone();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  if (!enabled) return null;
  return (
    <section className="lifecycle" aria-label={t("工单进度操作")}>
      <h3>{t("工单进度")}</h3>
      {!allowed.length ? (
        <p>{t("此工单已结束，保留历史，不能再更改状态。")}</p>
      ) : (
        <>
          <div className="approval-buttons">
            {allowed.map((s) => (
              <button
                key={s}
                className="secondary"
                disabled={busy || !ready}
                onClick={() => {
                  setTarget(s);
                  setBinding(order.version);
                  setConsent(false);
                }}
              >
                {orderStates[s]}
              </button>
            ))}
          </div>
          {!enabled && (
            <p className="availability-note">
              {t(
                "当前服务未开放此状态操作。可先查看操作影响，联系维护者确认版本。",
              )}
            </p>
          )}
          {target && (
            <div className="review-panel">
              <h3>
                {orderStates[target]}：「{order.summary}」
              </h3>
              <p>
                {["completed", "cancelled"].includes(target)
                  ? t(
                      "结束后释放预约时段，收尾自动待办、未发送草稿和待核对提议；保留历史。已派发的 WhatsApp 请求不会因此撤回。",
                    )
                  : t("只更新业务进度，不发送消息，也不代表客户确认了新安排。")}
              </p>
              <small>
                {t("本次核对工单 v")}
                {binding}
                {t("；当前 v")}
                {order.version}
              </small>
              {!current && (
                <p role="alert">{t("工单已变化，请关闭并重新选择操作。")}</p>
              )}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={!current || !ready || busy}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                {t("我已核对目标状态及影响")}
              </label>
              <button
                disabled={
                  !enabled ||
                  !consent ||
                  !current ||
                  !ready ||
                  busy ||
                  !!commands.attempt ||
                  !!commands.error
                }
                onClick={() => void submit()}
              >
                {t("保存工单状态")}
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setTarget(null)}
              >
                {t("关闭状态复核")}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
