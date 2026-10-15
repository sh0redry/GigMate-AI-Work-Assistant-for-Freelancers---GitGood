import type { components } from "./generated/api";
import { apiBase } from "./environment.ts";
import {
  allPages,
  workspaceApi,
  WorkspaceError,
  type Order,
  type Message,
  type Detail,
} from "./workspace-api.ts";

export type Action = components["schemas"]["ActionView"];
export type Conversation = components["schemas"]["Conversation"];
export type Operation = "approve" | "reject" | "cancel" | "reissue";
type Command =
  | components["schemas"]["ApproveActionCommand"]
  | components["schemas"]["RejectActionCommand"]
  | components["schemas"]["ReissueActionCommand"];
export type Attempt = {
  actionId: string;
  operation: Operation;
  key: string;
  hash: string;
  body: Command;
};
export type ApprovalSnapshot = {
  actions: Action[];
  orders: Order[];
  action: Action | null;
  order: Order | null;
  conversation: Conversation | null;
  messages: Message[];
  contextError: string;
};
export type ApprovalsApi = ReturnType<typeof approvalsApi>;
const states = new Set([
  "draft",
  "pending_approval",
  "approved",
  "executing",
  "succeeded",
  "failed",
  "result_unknown",
  "cancelled",
  "expired",
]);
const operations = new Set(["approve", "reject", "cancel", "reissue"]);
const hashPattern = /^sha256:[a-f0-9]{64}$/;
const positive = (n: unknown) => Number.isInteger(n) && Number(n) > 0;
function invalid(): never {
  throw new WorkspaceError(
    "INVALID_RESPONSE",
    "审批数据不完整，请刷新；当前不能批准。",
  );
}
function validAction(action: Action, accountId: string) {
  if (
    !action ||
    action.account_id !== accountId ||
    !action.id ||
    !action.work_order_id ||
    !action.conversation_id ||
    !action.recipient ||
    !action.body ||
    action.kind !== "send_text" ||
    !states.has(action.state) ||
    !positive(action.revision) ||
    !positive(action.bound_work_order_version) ||
    !positive(action.bound_context_version) ||
    !hashPattern.test(action.snapshot_hash) ||
    !Number.isFinite(Date.parse(action.expires_at)) ||
    !Array.isArray(action.sources) ||
    !action.sources.length ||
    action.sources.some((s) => !s.message_id || !positive(s.message_revision))
  )
    invalid();
}
function validAttempt(value: unknown): value is Attempt {
  if (!value || typeof value !== "object") return false;
  const a = value as Attempt;
  if (
    Object.keys(a).sort().join() !== "actionId,body,hash,key,operation" ||
    typeof a.actionId !== "string" ||
    !a.actionId ||
    typeof a.key !== "string" ||
    !/^[a-f0-9-]{36}$/.test(a.key) ||
    !operations.has(a.operation) ||
    !hashPattern.test(a.hash) ||
    !a.body ||
    typeof a.body !== "object"
  )
    return false;
  if (a.operation === "reissue")
    return (
      Object.keys(a.body).join() === "expected_context_version" &&
      positive(a.body.expected_context_version)
    );
  const b = a.body as components["schemas"]["RejectActionCommand"];
  const keys =
    a.operation === "approve"
      ? "expected_action_revision,expected_context_version,expected_version,snapshot_hash"
      : "expected_action_revision,expected_context_version,expected_version,reason,snapshot_hash";
  return (
    Object.keys(b).sort().join() === keys &&
    positive(b.expected_version) &&
    positive(b.expected_context_version) &&
    positive(b.expected_action_revision) &&
    b.snapshot_hash === a.hash &&
    (a.operation === "approve" ||
      (typeof b.reason === "string" &&
        b.reason.length > 0 &&
        b.reason.length <= 500))
  );
}
export function approvalsApi(
  csrf: string,
  accountId: string,
  fetcher: typeof fetch = fetch,
  providedStorage?: Storage | null,
) {
  const base = apiBase();
  const request = workspaceApi(csrf, fetcher);
  const storageKey = `gigmate-approval-attempt:${base}:${accountId}`;
  let attempt: Attempt | null = null;
  let storage: Storage | null = null;
  let storageError = "";
  let storageErrorCode = "UNRESOLVED_ATTEMPT";
  const failStorage = (message: string) => {
    storageError = message;
    storageErrorCode = "ATTEMPT_STORAGE_UNAVAILABLE";
  };
  // Reading the global property itself may throw SecurityError. Resolve it
  // inside the guard, never in a default parameter evaluated before the body.
  try {
    storage =
      providedStorage === undefined
        ? (globalThis.sessionStorage ?? null)
        : providedStorage;
    if (!storage) throw new Error();
  } catch {
    failStorage(
      "浏览器不允许保存原请求记录；可以查看审批，但当前不能提交操作。请恢复存储后重新打开页面，不能推断旧请求未提交。",
    );
  }
  let raw: string | null = null;
  if (!storageError) {
    try {
      raw = storage!.getItem(storageKey);
    } catch {
      failStorage(
        "原请求记录无法读取；可以查看审批，但当前不能提交操作。请恢复存储后重新核对旧请求。",
      );
    }
  }
  try {
    if (raw) {
      const value: unknown = JSON.parse(raw);
      if (!validAttempt(value)) throw new Error();
      attempt = value;
    }
  } catch {
    storageError =
      "原请求记录无法读取，请联系维护者核对；为避免重复批准，当前不能提交新操作。";
  }
  function persist(value: Attempt) {
    try {
      if (!storage) throw new Error();
      storage.setItem(storageKey, JSON.stringify(value));
      attempt = value;
    } catch {
      failStorage(
        "无法保存原请求记录；本次操作尚未提交，当前不能提交新操作。请恢复存储后重新打开审批页。",
      );
      throw new WorkspaceError("ATTEMPT_STORAGE_UNAVAILABLE", storageError);
    }
  }
  function clear() {
    try {
      if (!storage) throw new Error();
      // A stale adapter must not erase a newer intent written by another mount.
      const raw = storage.getItem(storageKey);
      if (raw !== null && raw !== JSON.stringify(attempt)) {
        failStorage(
          "原请求记录已被另一页面更新，本页不会删除它。操作响应已返回，请重新打开审批页核对。",
        );
        return;
      }
      if (raw !== null) storage.removeItem(storageKey);
      attempt = null;
    } catch {
      // The response was verified, but journal cleanup is not proof that the
      // old intent never committed. Retain it and block fresh submissions.
      failStorage(
        "操作响应已返回，但原请求记录无法清理；记录仍保留，当前不能提交新操作。请恢复存储后重新打开审批页核对。",
      );
    }
  }
  async function dispatch(original: Attempt, retry = false) {
    let response: Response;
    let result: Detail<Action> | { error?: { code?: string } } | null;
    try {
      response = await fetcher(
        `${base}/actions/${encodeURIComponent(original.actionId)}/${original.operation}`,
        {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          signal: AbortSignal.timeout(10000),
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf,
            "Idempotency-Key": original.key,
          },
          body: JSON.stringify(original.body),
        },
      );
      result = await response.json().catch(() => null);
    } catch {
      throw new WorkspaceError(
        "RESULT_UNKNOWN",
        "结果暂未确认。不要重新批准；刷新后核对，必要时使用原请求核对。",
      );
    }
    if (!response.ok) {
      if (response.status >= 500 || !result || !("error" in result))
        throw new WorkspaceError(
          "RESULT_UNKNOWN",
          "结果暂未确认，请保留原请求并核对，不能直接重发。",
        );
      const code =
        response.status === 401
          ? "UNAUTHENTICATED"
          : (result.error?.code ?? "REJECTED");
      // Authentication/CSRF rejection of a lookup attempt says nothing about
      // whether the preceding unknown request committed. Keep its identity.
      if (
        !retry ||
        (response.status === 409 &&
          ["APPROVAL_STALE", "VERSION_CONFLICT"].includes(code))
      )
        clear();
      throw new WorkspaceError(
        code,
        code === "UNAUTHENTICATED"
          ? "登录已过期，请重新登录；原记录仍按账号与环境保存。"
          : "后端拒绝了这次操作。请刷新后重新核对版本、来源、授权和当前状态。",
      );
    }
    if (!result || !("data" in result))
      throw new WorkspaceError(
        "RESULT_UNKNOWN",
        "响应不完整，暂时不能确认操作结果，请核对原请求。",
      );
    try {
      validAction(result.data, accountId);
    } catch {
      throw new WorkspaceError(
        "RESULT_UNKNOWN",
        "响应不完整，暂时不能确认操作结果，请核对原请求。",
      );
    }
    if (
      (original.operation !== "reissue" &&
        result.data.id !== original.actionId) ||
      (original.operation === "reissue" && result.data.id === original.actionId)
    )
      throw new WorkspaceError(
        "RESULT_UNKNOWN",
        "操作响应不匹配，保留原请求等待核对。",
      );
    const expectedState =
      original.operation === "approve"
        ? "approved"
        : original.operation === "reissue"
          ? "pending_approval"
          : "cancelled";
    if (
      result.data.state !== expectedState ||
      (original.operation !== "reissue" &&
        result.data.snapshot_hash !== original.hash)
    )
      throw new WorkspaceError(
        "RESULT_UNKNOWN",
        "结果状态或快照不匹配，原请求仍待核对。",
      );
    clear();
    return result.data;
  }
  return {
    attempt: () => attempt,
    storageError: () => storageError,
    async load(
      selected: string,
      signal: AbortSignal,
    ): Promise<ApprovalSnapshot> {
      const [actions, orders] = await Promise.all([
        allPages<Action>(request, "/actions", signal),
        allPages<Order>(request, "/work-orders", signal),
      ]);
      actions.forEach((a) => validAction(a, accountId));
      if (
        new Set(actions.map((a) => a.id)).size !== actions.length ||
        orders.some((o) => o.account_id !== accountId)
      )
        invalid();
      const id =
        selected ||
        attempt?.actionId ||
        actions.find((a) => a.state === "pending_approval")?.id ||
        actions[0]?.id;
      if (!id)
        return {
          actions,
          orders,
          action: null,
          order: null,
          conversation: null,
          messages: [],
          contextError: "",
        };
      const { data: action } = await request<Detail<Action>>(
        `/actions/${encodeURIComponent(id)}`,
        undefined,
        signal,
      );
      validAction(action, accountId);
      if (action.id !== id) invalid();
      const { data: order } = await request<Detail<Order>>(
        `/work-orders/${encodeURIComponent(action.work_order_id)}`,
        undefined,
        signal,
      );
      if (
        !order ||
        order.id !== action.work_order_id ||
        order.account_id !== accountId ||
        !Array.isArray(order.conversation_ids) ||
        !order.conversation_ids.includes(action.conversation_id)
      )
        invalid();
      let conversation: Conversation | null = null;
      let messages: Message[] = [];
      let contextError = "";
      try {
        conversation = (
          await request<Detail<Conversation>>(
            `/conversations/${encodeURIComponent(action.conversation_id)}`,
            undefined,
            signal,
          )
        ).data;
        if (
          !conversation ||
          conversation.id !== action.conversation_id ||
          conversation.account_id !== accountId ||
          !positive(conversation.context_version) ||
          !conversation.work_order_ids.includes(order.id)
        )
          invalid();
        messages = await allPages<Message>(
          request,
          `/conversations/${encodeURIComponent(action.conversation_id)}/messages`,
          signal,
        );
        if (
          messages.some(
            (m) =>
              m.account_id !== accountId ||
              m.conversation_id !== action.conversation_id,
          )
        )
          invalid();
      } catch (error) {
        if (
          !["NOT_FOUND", "CONSENT_REVOKED"].includes(
            (error as WorkspaceError).code,
          )
        )
          throw error;
        conversation = null;
        messages = [];
        contextError =
          "原文当前不可读取。可以拒绝／取消草稿，但不能批准或重新提问。";
      }
      const index = actions.findIndex((a) => a.id === action.id);
      if (index >= 0) actions[index] = action;
      else actions.push(action);
      return {
        actions,
        orders,
        action,
        order,
        conversation,
        messages,
        contextError,
      };
    },
    async submit(
      action: Action,
      operation: Operation,
      contextVersion: number,
      reason = "",
    ) {
      if (attempt || storageError)
        throw new WorkspaceError(
          attempt ? "UNRESOLVED_ATTEMPT" : storageErrorCode,
          storageError || "先核对原请求，再提交新操作。",
        );
      const snapshot = {
        expected_version: action.bound_work_order_version,
        expected_context_version: action.bound_context_version,
        expected_action_revision: action.revision,
        snapshot_hash: action.snapshot_hash,
      };
      const body: Command =
        operation === "reissue"
          ? { expected_context_version: contextVersion }
          : operation === "approve"
            ? snapshot
            : { ...snapshot, reason: reason.trim() };
      const original: Attempt = {
        actionId: action.id,
        operation,
        key: crypto.randomUUID(),
        hash: action.snapshot_hash,
        body,
      };
      if (!validAttempt(original))
        throw new WorkspaceError(
          "INVALID_COMMAND",
          "请填写 1 至 500 字的拒绝／取消原因。",
        );
      try {
        if (storage?.getItem(storageKey))
          throw new WorkspaceError(
            "UNRESOLVED_ATTEMPT",
            "另一个页面已记录原请求，请重新打开审批页核对。",
          );
      } catch (error) {
        if (error instanceof WorkspaceError) throw error;
        failStorage(
          "无法核对浏览器原请求记录；本次操作尚未提交，当前不能提交新操作。请恢复存储后重新打开页面。",
        );
        throw new WorkspaceError("ATTEMPT_STORAGE_UNAVAILABLE", storageError);
      }
      persist(original);
      return dispatch(original);
    },
    retryOriginal() {
      if (!attempt || storageError)
        throw new WorkspaceError("NO_ORIGINAL_REQUEST", "没有可核对的原请求。");
      return dispatch(attempt, true);
    },
  };
}
