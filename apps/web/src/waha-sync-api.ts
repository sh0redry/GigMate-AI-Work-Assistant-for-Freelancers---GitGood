import { ConnectionError } from "./connection-api";
import type { components } from "./generated/api";

export type SyncJob = components["schemas"]["WahaSyncResult"];
export type SyncCommand = components["schemas"]["WahaSyncCommand"];
export type TimelineMessage = components["schemas"]["WahaTimelineMessage"];
export type SourceGap = components["schemas"]["WahaSourceGapView"];
type Page<T> = { items: T[]; next_cursor: string | null };

export function synchronizationApi(connection: string, csrf: string) {
  const base = `/api/v1/connectors/${encodeURIComponent(connection)}`;
  const attempts = new Map<string, SyncCommand>();
  async function request<T>(
    path: string,
    body?: object,
    key?: string,
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch(base + path, {
        method: body ? "POST" : "GET",
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
        body ? "SYNC_RESULT_UNCERTAIN" : "NETWORK_ERROR",
        "查询失败，请刷新；同步请求重试须保留原请求。",
      );
    }
    const result = await response.json();
    if (response.status === 404 && !result.error)
      throw new ConnectionError(
        "SYNC_API_UNAVAILABLE",
        "同步接口尚不可用，请先完成本批次后端迁移并重建服务。",
      );
    if (!response.ok)
      throw new ConnectionError(
        result.error?.code ?? "HTTP_ERROR",
        result.error?.message ?? "请求失败",
      );
    return result;
  }
  async function setup() {
    return (
      await request<{ data: components["schemas"]["WahaSetup"] }>("/setup")
    ).data;
  }
  return {
    setup,
    async chats() {
      return (
        await request<{ data: components["schemas"]["WahaChoice"][] }>("/chats")
      ).data.filter((c) => c.selected);
    },
    jobs: () => request<Page<SyncJob>>("/sync-jobs?limit=100"),
    gaps: () => request<Page<SourceGap>>("/source-gaps?limit=100"),
    timeline: (chat: string, cursor: string | null = null) =>
      request<Page<TimelineMessage>>(
        `/chats/${encodeURIComponent(chat)}/timeline?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      ),
    async start(value: Omit<SyncCommand, "expected_version">, key: string) {
      let command = attempts.get(key);
      if (!command) {
        command = {
          ...value,
          expected_version: (await setup()).control_version,
        };
        attempts.set(key, command);
      } else if (
        JSON.stringify({ ...command, expected_version: undefined }) !==
        JSON.stringify(value)
      )
        throw new ConnectionError(
          "IDEMPOTENCY_CONFLICT",
          "原同步请求尚待核对，请保留原参数后重试。",
        );
      return (await request<{ data: SyncJob }>("/sync-jobs", command, key))
        .data;
    },
    async cancel(id: string) {
      return (
        await request<{ data: SyncJob }>(
          `/sync-jobs/${encodeURIComponent(id)}/cancel`,
          { expected_version: (await setup()).control_version },
        )
      ).data;
    },
  };
}
