import { useState } from "react";
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
        body: { status: target, expected_version: order.version },
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
  return (
    <section className="lifecycle" aria-label="工单进度操作">
      <h3>工单进度</h3>
      {!allowed.length ? (
        <p>此工单已结束，保留历史，不能再更改状态。</p>
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
              暂不可保存：等待 C
              的工单状态接口（#27）完成修复并验收。可以先查看每个操作的影响。
            </p>
          )}
          {target && (
            <div className="review-panel">
              <h3>
                {orderStates[target]}：「{order.summary}」
              </h3>
              <p>
                {["completed", "cancelled"].includes(target)
                  ? "结束后释放预约时段，收尾自动待办、未发送草稿和待核对提议；保留历史。已派发的 WhatsApp 请求不会因此撤回。"
                  : "只更新业务进度，不发送消息，也不代表客户确认了新安排。"}
              </p>
              <small>
                本次核对工单 v{binding}；当前 v{order.version}
              </small>
              {!current && (
                <p role="alert">工单已变化，请关闭并重新选择操作。</p>
              )}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={!current || !ready || busy}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                我已核对目标状态及影响
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
                保存工单状态
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setTarget(null)}
              >
                关闭状态复核
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
