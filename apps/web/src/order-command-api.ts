import { apiBase } from "./environment.ts";
import { WorkspaceError, type Order } from "./workspace-api.ts";
import type { components } from "./generated/api";
// #26/#27 are target contracts, not implemented main routes. Release capability
// gates keep these commands off until C publishes and accepts the same shapes.
export type CreateOrderInput = {
  conversation_id: string;
  summary: string;
  schedule:
    | components["schemas"]["TimedSchedule"]
    | components["schemas"]["DateOnly"]
    | null;
  schedule_sources: components["schemas"]["SourceRef"][];
  address: string | null;
  address_sources: components["schemas"]["SourceRef"][];
  confirm_additional_order: boolean;
};
export type OrderTarget =
  | "in_progress"
  | "waiting_customer"
  | "completed"
  | "cancelled";
export type Intent =
  | { kind: "create"; body: CreateOrderInput }
  | {
      kind: "status";
      orderId: string;
      body: { expected_version: number; status: OrderTarget };
    }
  | {
      kind: "confirm";
      orderId: string;
      changeId: string;
      review: {
        summary: string;
        oldValue: unknown;
        newValue: unknown;
        sources: components["schemas"]["SourceRef"][];
      };
      body: components["schemas"]["ConfirmChangeCommand"];
    };
type Attempt = { intent: Intent; key: string };
const idPattern = /^[a-f0-9-]{36}$/i;
function valid(a: Attempt) {
  if (
    !a ||
    Object.keys(a).sort().join() !== "intent,key" ||
    !idPattern.test(a.key) ||
    !a.intent ||
    !a.intent.body
  )
    return false;
  const i = a.intent;
  if (i.kind === "create")
    return (
      Object.keys(i).sort().join() === "body,kind" &&
      idPattern.test(i.body.conversation_id) &&
      typeof i.body.summary === "string" &&
      i.body.summary.trim().length > 0 &&
      i.body.summary.length <= 120 &&
      Array.isArray(i.body.schedule_sources) &&
      Array.isArray(i.body.address_sources) &&
      typeof i.body.confirm_additional_order === "boolean"
    );
  return (
    ["status", "confirm"].includes(i.kind) &&
    idPattern.test(i.orderId) &&
    Number.isInteger(i.body.expected_version) &&
    i.body.expected_version > 0 &&
    (i.kind === "status"
      ? ["in_progress", "waiting_customer", "completed", "cancelled"].includes(
          i.body.status,
        )
      : idPattern.test(i.changeId) &&
        !!i.review &&
        typeof i.review.summary === "string" &&
        Array.isArray(i.review.sources) &&
        Number.isInteger(i.body.expected_context_version) &&
        i.body.expected_context_version > 0 &&
        i.body.apply_calendar_update === true)
  );
}
function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const left = a as Record<string, unknown>,
    right = b as Record<string, unknown>;
  const keys = Object.keys(left).sort();
  return (
    JSON.stringify(keys) === JSON.stringify(Object.keys(right).sort()) &&
    keys.every((key) => sameValue(left[key], right[key]))
  );
}
export function orderCommands(
  csrf: string,
  accountId: string,
  fetcher: typeof fetch = fetch,
  provided?: Storage | null,
) {
  const base = apiBase(),
    name = `gigmate-order-attempt:${base}:${accountId}`;
  let storage: Storage | null = null,
    attempt: Attempt | null = null,
    error = "",
    busy = false;
  try {
    storage = provided === undefined ? globalThis.sessionStorage : provided;
    if (!storage) throw new Error();
    const raw = storage.getItem(name);
    if (raw) {
      const value = JSON.parse(raw);
      if (!valid(value)) throw new Error();
      attempt = value;
    }
  } catch {
    error =
      "浏览器无法保存或读取原操作。可以查看数据，暂不能提交；恢复存储后重新打开并核对。";
  }
  function fail(code: string, message: string): never {
    throw new WorkspaceError(code, message);
  }
  function checkStorage() {
    try {
      if (
        !storage ||
        storage.getItem(name) !== (attempt ? JSON.stringify(attempt) : null)
      )
        throw new Error();
    } catch {
      error = "原操作记录不可用或已被另一页面改变，请恢复后重新打开核对。";
      fail("ATTEMPT_STORAGE_UNAVAILABLE", error);
    }
  }
  function clear() {
    checkStorage();
    try {
      storage!.removeItem(name);
      attempt = null;
    } catch {
      error =
        "操作响应已核对，但原记录清理失败。禁止新提交，请恢复存储后核对原编号。";
      fail("ATTEMPT_STORAGE_UNAVAILABLE", error);
    }
  }
  async function dispatch(retry: boolean) {
    const saved = attempt!;
    checkStorage();
    busy = true;
    const i = saved.intent,
      path =
        i.kind === "create"
          ? "/work-orders"
          : i.kind === "status"
            ? `/work-orders/${i.orderId}/status`
            : `/work-orders/${i.orderId}/changes/${i.changeId}/confirm`;
    try {
      const response = await fetcher(base + path, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          "Idempotency-Key": saved.key,
        },
        body: JSON.stringify(i.body),
      });
      const value = await response.json().catch(() => null);
      if (!response.ok) {
        const code =
          response.status === 401
            ? "UNAUTHENTICATED"
            : (value?.error?.code ?? "RESULT_UNKNOWN");
        if (
          !retry &&
          [
            "VALIDATION_FAILED",
            "NOT_FOUND",
            "CONSENT_REVOKED",
            "VERSION_CONFLICT",
            "APPROVAL_STALE",
            "SCHEDULE_CONFLICT",
            "OPEN_ORDER_EXISTS",
            "INVALID_TRANSITION",
          ].includes(code)
        )
          clear();
        fail(
          code,
          code === "OPEN_ORDER_EXISTS"
            ? "该会话已有未结束工单，请刷新查看；另开一单需要再次明确确认。"
            : code === "SCHEDULE_CONFLICT"
              ? "时间与已有预约冲突，请核对日历后修改。"
              : code === "UNAUTHENTICATED"
                ? "登录已过期；原操作记录保留，请重新登录核对。"
                : "操作未确认完成，请刷新；若保留了原编号，只能明确核对该原操作。",
        );
      }
      const order = value?.data as Order;
      if (
        !order ||
        order.account_id !== accountId ||
        !idPattern.test(order.id) ||
        !Array.isArray(order.conversation_ids) ||
        !order.fields ||
        !order.fields.schedule ||
        !order.fields.address ||
        !Number.isInteger(order.version) ||
        (i.kind !== "create" &&
          (order.id !== i.orderId ||
            order.version !== i.body.expected_version + 1)) ||
        (i.kind === "status" && order.status !== i.body.status) ||
        (i.kind === "confirm" &&
          (order.fields.schedule.status !== "confirmed" ||
            !sameValue(order.fields.schedule.value, i.review.newValue))) ||
        (i.kind === "create" &&
          (!order.conversation_ids.includes(i.body.conversation_id) ||
            order.summary !== i.body.summary ||
            !sameValue(order.fields.schedule.value, i.body.schedule) ||
            order.fields.address.value !== i.body.address))
      )
        fail(
          "RESULT_UNKNOWN",
          "响应无法完整核对，原请求保留；请勿重复创建或确认。",
        );
      clear();
      return order;
    } catch (e) {
      if (e instanceof WorkspaceError) throw e;
      fail(
        "RESULT_UNKNOWN",
        "连接中断，无法确定是否已保存。原请求已保留，请恢复服务后核对，勿重复提交。",
      );
    } finally {
      busy = false;
    }
  }
  return {
    get attempt() {
      return attempt;
    },
    get error() {
      return error;
    },
    async submit(intent: Intent) {
      if (error || attempt || busy)
        fail(
          "UNRESOLVED_ATTEMPT",
          error || "先核对已有原操作，不能提交新操作。",
        );
      checkStorage();
      const next = {
        intent: structuredClone(intent),
        key: crypto.randomUUID(),
      };
      if (!valid(next)) fail("VALIDATION_FAILED", "操作内容无效，请重新核对。");
      try {
        storage!.setItem(name, JSON.stringify(next));
        attempt = next;
      } catch {
        error = "原操作无法安全保存，本次未提交。";
        fail("ATTEMPT_STORAGE_UNAVAILABLE", error);
      }
      return dispatch(false);
    },
    async retry() {
      if (error || busy || !attempt)
        fail("UNRESOLVED_ATTEMPT", error || "没有可核对的原操作。");
      return dispatch(true);
    },
  };
}
export type OrderCommands = ReturnType<typeof orderCommands>;
