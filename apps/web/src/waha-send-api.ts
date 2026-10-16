import { sessionFetch } from "./read-cache.ts";
import { ConnectionError } from "./connection-api";
import { apiBase } from "./environment.ts";
import type { components } from "./generated/api";

export type SendPayload = components["schemas"]["WahaSendPayload"];
export type SendAction = components["schemas"]["WahaSendActionView"];
export type SendPolicy = components["schemas"]["WahaSendPolicyView"];
export type SendUpload = components["schemas"]["WahaSendUploadView"];
export type SendDraft = components["schemas"]["WahaSendDraftCommand"];
export type SendPermission = components["schemas"]["WahaSendPermissionView"];
type Capabilities = components["schemas"]["WahaSendCapabilities"];
type PolicyCommand = components["schemas"]["WahaSendPolicyCommand"];
type PermissionCommand = components["schemas"]["WahaSendPermissionCommand"];
type RequestView = components["schemas"]["WahaSendRequestView"];
type Page<T> = { items: T[]; next_cursor: string | null };

export function sendingMime(file: Pick<File, "name" | "type">, override = "") {
  if (override.trim()) return override.trim();
  const byExtension: Record<string, string> = {
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    png: "image/png",
    webp: "image/webp",
    ogg: "audio/ogg",
    opus: "audio/ogg",
    mp3: "audio/mpeg",
    wav: "audio/wav",
    m4a: "audio/mp4",
    mp4: "video/mp4",
    pdf: "application/pdf",
    txt: "text/plain",
    csv: "text/csv",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  };
  // This is only a declaration; the server validates extension and bounded bytes.
  return (
    byExtension[file.name.split(".").pop()?.toLowerCase() ?? ""] ?? file.type
  );
}

export function sendingApi(connection: string, csrf: string) {
  const base = `${apiBase()}/connectors/${encodeURIComponent(connection)}/sending`;
  async function request<T>(
    path: string,
    body?: object | File,
    key?: string,
    uploadHeaders?: Record<string, string>,
  ): Promise<T> {
    let response: Response;
    try {
      response = await sessionFetch(base + path, {
        method: body ? "POST" : "GET",
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(30000),
        headers: body
          ? {
              "X-CSRF-Token": csrf,
              "Content-Type":
                path === "/uploads"
                  ? "application/octet-stream"
                  : "application/json",
              ...(key ? { "Idempotency-Key": key } : {}),
              ...uploadHeaders,
            }
          : {},
        body:
          path === "/uploads"
            ? (body as File)
            : body
              ? JSON.stringify(body)
              : undefined,
      });
    } catch {
      throw new ConnectionError(
        body ? "SEND_REQUEST_UNKNOWN" : "NETWORK_ERROR",
        "请求结果待核对，请刷新已有记录，不要另建发送任务。",
      );
    }
    const data = await response.json().catch(() => null);
    if (!response.ok || !data)
      throw new ConnectionError(
        !data && body && response.ok
          ? "SEND_REQUEST_UNKNOWN"
          : response.status === 401
            ? "UNAUTHENTICATED"
            : body && response.status >= 500
              ? "SEND_REQUEST_UNKNOWN"
              : (data?.error?.code ?? "SEND_API_UNAVAILABLE"),
        "发送操作未完成，请核对权限和已有记录。",
      );
    return data;
  }
  async function detail<T>(
    path: string,
    body?: object | File,
    key?: string,
    uploadHeaders?: Record<string, string>,
  ): Promise<T> {
    const response = await request<{ data: T }>(path, body, key, uploadHeaders);
    if (!response.data)
      throw new ConnectionError(
        body ? "SEND_REQUEST_UNKNOWN" : "INVALID_RESPONSE",
        "响应不完整，请核对已有记录。",
      );
    return response.data;
  }
  function checkedAction(
    value: SendAction,
    expected?: { id?: string; chat_id?: string },
  ): SendAction {
    if (
      !value ||
      typeof value.id !== "string" ||
      !/^[a-f0-9-]{36}$/i.test(value.id) ||
      !value.payload ||
      ![
        "draft",
        "queued",
        "preparing",
        "dispatching",
        "accepted",
        "failed",
        "cancelled",
        "result_unknown",
      ].includes(value.state) ||
      (expected?.id && value.id !== expected.id) ||
      (expected?.chat_id && value.chat_id !== expected.chat_id)
    )
      throw new ConnectionError(
        "SEND_REQUEST_UNKNOWN",
        "发送响应无法核对，请读取原请求记录。",
      );
    return value;
  }
  return {
    capabilities: () => detail<Capabilities>("/capabilities"),
    permission: () => detail<SendPermission>("/permission"),
    setPermission: (value: PermissionCommand) =>
      detail<SendPermission>("/permission", value),
    context: (chat: string) =>
      detail<{ context_version: number; control_version: number }>(
        `/context/${encodeURIComponent(chat)}`,
      ),
    async draft(value: SendDraft, key: string) {
      return checkedAction(await detail<SendAction>("/drafts", value, key), {
        chat_id: value.chat_id,
      });
    },
    request: (key: string) =>
      detail<RequestView>(`/requests/${encodeURIComponent(key)}`),
    cancelRequest: (key: string) =>
      detail<RequestView>(`/requests/${encodeURIComponent(key)}/cancel`, {}),
    action: (id: string) =>
      detail<SendAction>(`/actions/${encodeURIComponent(id)}`),
    actions: (cursor: string | null = null, chat?: string) =>
      request<Page<SendAction>>(
        `/actions?${new URLSearchParams({ ...(cursor ? { cursor } : {}), ...(chat ? { chat_id: chat } : {}) })}`,
      ),
    policies: (cursor: string | null = null, chat?: string) =>
      request<Page<SendPolicy>>(
        `/policies?${new URLSearchParams({ ...(cursor ? { cursor } : {}), ...(chat ? { chat_id: chat } : {}) })}`,
      ),
    createPolicy: (value: PolicyCommand) =>
      detail<SendPolicy>("/policies", value),
    revokePolicy: (p: SendPolicy) =>
      detail<SendPolicy>(`/policies/${p.id}/revoke`, {
        expected_revision: p.version,
      }),
    async mutate(a: SendAction, operation: "approve" | "cancel" | "reconcile") {
      return checkedAction(
        await detail<SendAction>(`/actions/${a.id}/${operation}`, {
          expected_revision: a.revision,
        }),
        { id: a.id, chat_id: a.chat_id },
      );
    },
    reviewUnknown: (a: SendAction, note: string) =>
      detail<SendAction>(`/actions/${a.id}/review-unknown`, {
        expected_revision: a.revision,
        acknowledge_possible_delivery: true,
        note,
      }),
    upload: (file: File, mime: string) =>
      detail<SendUpload>("/uploads", file, undefined, {
        "X-File-Name": encodeURIComponent(file.name),
        "X-File-Mimetype": mime,
      }),
    previewUrl: (id: string) =>
      `${base}/uploads/${encodeURIComponent(id)}/content`,
  };
}
