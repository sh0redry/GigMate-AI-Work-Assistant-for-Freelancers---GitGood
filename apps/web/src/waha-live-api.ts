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

// Only canonical backend endpoints. No subprocess, WAHA key or local profile.
export function liveConnectionApi(csrf: string): ConnectionApi {
  const attempts = new Map<string, Command>();
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
    return (await response(path, method, body, key)).json();
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
          : (op.error_code ?? "OPERATION_PENDING"),
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
    const cacheKey = `${id}:${key}`;
    let body = attempts.get(cacheKey);
    if (!body) {
      body = { action, expected_version: (await setup(id)).control_version };
      if (action === "discover" && offset > 0)
        body = { ...body, offset, limit: 100 };
      attempts.set(cacheKey, body); // Preserve the exact body if the response is lost.
    }
    if (body.action !== action || (body.offset ?? 0) !== offset)
      throw new ConnectionError(
        "IDEMPOTENCY_CONFLICT",
        "请求键已用于其他操作。",
      );
    return wait(
      id,
      (
        await request<Detail<Operation>>(
          base(id) + "/operations",
          "POST",
          body,
          key,
        )
      ).data,
    );
  }
  function pairingView(value: Setup, op: Operation | null = null): Pairing {
    const unknown = op?.state === "result_unknown";
    const state = unknown
      ? "RESULT_UNKNOWN"
      : (value.provider_state ?? "unknown");
    return {
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
        state === "SCAN_QR_CODE",
      available: value.available,
      provider_sample_stale: value.provider_sample_stale,
      operation_id: op?.id ?? null,
      operation_state: op?.state ?? null,
    };
  }
  async function pairing(id: string, force = false): Promise<Pairing> {
    let value = await setup(id);
    let op: Operation | null = null;
    if (value.active_operation_id) {
      op = (
        await request<Detail<Operation>>(
          base(id) + `/operations/${value.active_operation_id}`,
        )
      ).data;
    } else if (value.available && (value.provider_sample_stale || force)) {
      await operate(id, "inspect", crypto.randomUUID());
      value = await setup(id);
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
    do {
      const page: Page<T> = await request(
        `${path}?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      );
      result.push(...page.items);
      cursor = page.next_cursor;
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
