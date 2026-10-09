import {
  ConnectionError,
  type ConnectionApi,
  type Choice,
  type Pairing,
} from "./connection-api";
import type { components } from "./generated/api";

type Setup = components["schemas"]["WahaSetup"];
type Operation = components["schemas"]["WahaControlResult"];
type CommandShape = components["schemas"]["WahaControlCommand"];
// Defaulted pagination is optional on the wire; retain compact legacy commands.
type Command = Omit<CommandShape, "offset" | "limit"> &
  Partial<Pick<CommandShape, "offset" | "limit">>;
type Detail<T> = { data: T };
type Page<T> = { items: T[]; next_cursor: string | null };
type Attempt = { key: string; body: Command };
const storagePrefix = "gigmate-control-attempt:";
function storage() {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}
// Only opaque app IDs and the exact request body/key; never credentials or QR.
export function clearConnectionAttempts() {
  const target = storage();
  if (!target) return;
  try {
    for (let i = target.length - 1; i >= 0; i--) {
      const key = target.key(i);
      if (key?.startsWith(storagePrefix)) target.removeItem(key);
    }
  } catch {
    /* Storage can be disabled. Account state is still cleared by logout. */
  }
}

// Only canonical backend endpoints. No subprocess, WAHA key or local profile.
export function liveConnectionApi(csrf: string): ConnectionApi {
  const attempts = new Map<string, Attempt>();
  function attempt(id: string) {
    if (!attempts.has(id)) {
      try {
        const value = JSON.parse(
          storage()?.getItem(storagePrefix + id) ?? "null",
        );
        if (
          typeof value?.key === "string" &&
          ["connect", "recover", "inspect", "discover"].includes(
            value?.body?.action,
          ) &&
          Number.isInteger(value?.body?.expected_version) &&
          value.body.expected_version >= 0 &&
          (value.body.offset === undefined ||
            (value.body.action === "discover" &&
              Number.isInteger(value.body.offset) &&
              value.body.offset >= 0 &&
              value.body.offset <= 10000)) &&
          (value.body.limit === undefined ||
            (value.body.action === "discover" &&
              Number.isInteger(value.body.limit) &&
              value.body.limit >= 1 &&
              value.body.limit <= 100))
        )
          attempts.set(id, {
            key: value.key,
            body: {
              action: value.body.action,
              expected_version: value.body.expected_version,
              ...(value.body.offset === undefined
                ? {}
                : { offset: value.body.offset }),
              ...(value.body.limit === undefined
                ? {}
                : { limit: value.body.limit }),
            },
          });
      } catch {
        /* Storage is optional; durable server intent remains authoritative. */
      }
    }
    return attempts.get(id);
  }
  function remember(id: string, value: Attempt | null) {
    if (value) attempts.set(id, value);
    else attempts.delete(id);
    try {
      if (value) storage()?.setItem(storagePrefix + id, JSON.stringify(value));
      else storage()?.removeItem(storagePrefix + id);
    } catch {
      /* Browser storage can be unavailable. Keep the in-memory attempt. */
    }
  }
  const base = (id: string) => `/connectors/${encodeURIComponent(id)}`;
  async function response(
    path: string,
    method = "GET",
    body?: object,
    key?: string,
  ) {
    let value: Response;
    try {
      value = await fetch(`/api/v1${path}`, {
        method,
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
        headers: body
          ? {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrf,
              ...(key ? { "Idempotency-Key": key } : {}),
            }
          : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ConnectionError(
        method === "GET" ? "NETWORK_ERROR" : "OPERATION_RESULT_UNKNOWN",
        "请求结果待确认，请刷新状态；不要另建请求重试。",
      );
    }
    if (!value.ok) {
      const error = await value.json().catch(() => ({}));
      throw new ConnectionError(
        value.status === 401
          ? "UNAUTHENTICATED"
          : method !== "GET" && value.status >= 500
            ? "OPERATION_RESULT_UNKNOWN"
            : (error.error?.code ?? "HTTP_ERROR"),
        error.error?.message ?? "请求失败",
        error.request_id,
      );
    }
    return value;
  }
  async function request<T>(
    path: string,
    method = "GET",
    body?: object,
    key?: string,
  ): Promise<T> {
    const value = await response(path, method, body, key);
    try {
      return await value.json();
    } catch {
      throw new ConnectionError(
        method === "GET" ? "INVALID_RESPONSE" : "OPERATION_RESULT_UNKNOWN",
        "响应未能完整读取，请重新核对状态；不要另建请求重试。",
      );
    }
  }
  const setup = async (id: string) =>
    (await request<Detail<Setup>>(base(id) + "/setup")).data;
  const catalog = async (id: string) =>
    (await request<Detail<Choice[]>>(base(id) + "/chats")).data;
  async function wait(id: string, initial: Operation): Promise<Operation> {
    let op = initial;
    const deadline = Date.now() + 45000;
    while (
      ["pending", "running", "checking"].includes(op.state) &&
      Date.now() < deadline
    ) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      op = (await request<Detail<Operation>>(base(id) + `/operations/${op.id}`))
        .data;
    }
    if (op.state !== "succeeded") {
      throw new ConnectionError(
        op.state === "result_unknown"
          ? "WAHA_OPERATION_NEEDS_RECONCILIATION"
          : (op.error_code ??
              (op.state === "cancelled"
                ? "WAHA_OPERATION_CANCELLED"
                : op.state === "failed"
                  ? "WAHA_OPERATION_FAILED"
                  : "OPERATION_PENDING")),
        "操作尚未完成，请刷新状态或明确核对；不要重复提交。",
      );
    }
    return op;
  }
  async function operate(
    id: string,
    action: Command["action"],
    key: string,
    offset = 0,
  ) {
    let value = attempt(id);
    if (
      value &&
      (value.key !== key ||
        value.body.action !== action ||
        (value.body.offset ?? 0) !== offset)
    ) {
      throw new ConnectionError(
        "OPERATION_RESULT_UNKNOWN",
        "上次请求结果待确认，请使用原请求核对。",
      );
    }
    if (!value) {
      value = {
        key,
        body: { action, expected_version: (await setup(id)).control_version },
      };
      if (action === "discover" && offset > 0)
        value.body = { ...value.body, offset, limit: 100 };
      remember(id, value);
    }
    let op: Operation;
    try {
      op = (
        await request<Detail<Operation>>(
          base(id) + "/operations",
          "POST",
          value.body,
          value.key,
        )
      ).data;
      if (
        !op ||
        typeof op.id !== "string" ||
        ![
          "pending",
          "running",
          "checking",
          "succeeded",
          "failed",
          "result_unknown",
          "cancelled",
        ].includes(op.state)
      )
        throw new ConnectionError(
          "OPERATION_RESULT_UNKNOWN",
          "未能读取操作编号，请使用原请求核对。",
        );
      remember(id, null); // The server operation UUID now permits read-only polling.
    } catch (error) {
      if (
        !(error instanceof ConnectionError) ||
        error.code !== "OPERATION_RESULT_UNKNOWN"
      )
        remember(id, null);
      throw error;
    }
    return wait(id, op);
  }
  function pairingView(value: Setup, op: Operation | null = null): Pairing {
    const unknown = op?.state === "result_unknown";
    const state = unknown
      ? "RESULT_UNKNOWN"
      : (value.provider_state ?? "unknown");
    return {
      enabled: value.enabled,
      control_version: value.control_version,
      state,
      connected:
        value.enabled &&
        !value.provider_sample_stale &&
        !unknown &&
        state === "WORKING",
      qr_available:
        value.enabled &&
        !value.provider_sample_stale &&
        !unknown &&
        !attempt(value.connection_id) &&
        state === "SCAN_QR_CODE",
      available: value.available,
      provider_sample_stale: value.provider_sample_stale,
      operation_id: value.active_operation_id,
      operation_state: op?.state ?? null,
      operation_action: op?.action ?? null,
      operation_error: op?.error_code ?? null,
      retry_available: !!attempt(value.connection_id),
    };
  }
  async function pairing(id: string, force = false): Promise<Pairing> {
    let value = await setup(id);
    let op: Operation | null = null;
    const operationId = value.active_operation_id ?? value.last_operation_id;
    if (operationId) {
      op = (
        await request<Detail<Operation>>(
          base(id) + `/operations/${operationId}`,
        )
      ).data;
    }
    if (
      !value.active_operation_id &&
      !attempt(id) &&
      value.enabled &&
      value.available &&
      (force ||
        (value.provider_state !== null &&
          value.provider_sample_stale &&
          op?.state !== "failed"))
    ) {
      try {
        await operate(id, "inspect", crypto.randomUUID());
      } catch (error) {
        if (
          error instanceof ConnectionError &&
          error.code === "UNAUTHENTICATED"
        )
          throw error;
        // Keep setup availability/authority even when provider inspection fails.
        // The persisted outcome or original-request marker explains the failure.
      }
      value = await setup(id);
      op = value.last_operation_id
        ? (
            await request<Detail<Operation>>(
              base(id) + `/operations/${value.last_operation_id}`,
            )
          ).data
        : null;
    }
    return pairingView(value, op);
  }
  async function selection(id: string) {
    const value = await setup(id),
      choices = await catalog(id);
    return {
      control_version: value.control_version,
      selected: choices.filter((choice) => choice.selected),
      choices,
    };
  }
  async function pages<T>(path: string): Promise<T[]> {
    let cursor: string | null = null;
    const result: T[] = [];
    const seen = new Set<string>();
    do {
      const page: Page<T> = await request(
        `${path}?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      );
      if (
        !page ||
        !Array.isArray(page.items) ||
        (page.next_cursor !== null && typeof page.next_cursor !== "string")
      )
        throw new ConnectionError(
          "INVALID_RESPONSE",
          "列表数据无效，请刷新后重试。",
        );
      result.push(...page.items);
      cursor = page.next_cursor;
      if (cursor && seen.has(cursor))
        throw new ConnectionError(
          "INVALID_RESPONSE",
          "列表分页异常，请刷新后重试。",
        );
      if (cursor) seen.add(cursor);
    } while (cursor);
    return result;
  }
  return {
    capabilities: {
      pairing: true,
      start: !!csrf,
      selection: !!csrf,
      recovery: !!csrf,
    },
    connectors: () => pages("/connectors"),
    pairing,
    async start(id, key) {
      await operate(id, "connect", key);
      return pairing(id);
    },
    async restart(id, key) {
      await operate(id, "recover", key);
    },
    async retry(id) {
      const value = attempt(id);
      if (!value)
        throw new ConnectionError(
          "WAHA_RECONCILIATION_NOT_REQUIRED",
          "没有待核对的原请求。",
        );
      const op = await operate(
        id,
        value.body.action,
        value.key,
        value.body.offset ?? 0,
      );
      if (value.body.action === "discover")
        return {
          items: await catalog(id),
          next_offset: op.next_offset ?? null,
        };
    },
    async reconcile(id) {
      const value = await setup(id);
      if (!value.active_operation_id)
        throw new ConnectionError(
          "WAHA_RECONCILIATION_NOT_REQUIRED",
          "没有待核对操作。",
        );
      const op = (
        await request<Detail<Operation>>(
          base(id) + `/operations/${value.active_operation_id}/reconcile`,
          "POST",
          { expected_version: value.control_version },
        )
      ).data;
      await wait(id, op);
    },
    async pause(id) {
      await request(base(id) + "/pause", "POST", {
        expected_version: (await setup(id)).control_version,
      });
    },
    async resume(id) {
      await request(base(id) + "/resume", "POST", {
        expected_version: (await setup(id)).control_version,
      });
    },
    async qr(id) {
      const image = await (await response(base(id) + "/qr")).blob();
      if (
        image.type !== "image/png" ||
        !image.size ||
        image.size > 2 * 1024 * 1024
      )
        throw new ConnectionError("WAHA_INVALID_QR", "二维码图片无效。");
      return image;
    },
    selection,
    async chats(id, offset) {
      const op = await operate(id, "discover", crypto.randomUUID(), offset);
      return { items: await catalog(id), next_offset: op.next_offset ?? null };
    },
    async save(id, value, choices) {
      await request(base(id) + "/chats", "PUT", {
        expected_version: value.control_version,
        selected_ids: choices.map((choice) => choice.id),
        consent: true,
      });
      return selection(id);
    },
    issues: (id) => pages(base(id) + "/recovery-issues"),
    async reviewIssues(id, issueIds) {
      const result = await request<
        Detail<components["schemas"]["WahaIssueReviewResult"]>
      >(base(id) + "/recovery-issues/review", "POST", {
        issue_ids: issueIds,
        confirmed_no_import: true,
      });
      return result.data.reviewed;
    },
  };
}
