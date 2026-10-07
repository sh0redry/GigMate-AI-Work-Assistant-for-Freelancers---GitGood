import type { components } from "./generated/api";

export type Connector = components["schemas"]["ConnectorStatus"];
export type Issue = components["schemas"]["RecoveryIssue"];
// Frontend-only preview shapes. These are proposals, not shared API contracts.
// Replace them with generated types after Andy publishes the corresponding API.
export type Pairing = {
  state: string;
  connected: boolean;
  qr_available: boolean;
};
export type Choice = {
  choice_id: string;
  token: string;
  name: string;
  kind: "direct" | "group";
  selected: boolean;
  conversation_id: string | null;
};
export type Selection = { version: number; selected: Choice[] };
export type Discovery = { items: Choice[]; next_offset: number | null };
type Page<T> = { items: T[]; next_cursor: string | null };

export class ConnectionError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}
export interface ConnectionApi {
  readonly capabilities: {
    pairing: boolean;
    start: boolean;
    selection: boolean;
  };
  connectors(): Promise<Connector[]>;
  pairing(id: string): Promise<Pairing>;
  start(id: string, key: string): Promise<Pairing>;
  qr(id: string): Promise<Blob>;
  selection(id: string): Promise<Selection>;
  chats(id: string, offset: number): Promise<Discovery>;
  save(
    id: string,
    value: Selection,
    choices: Choice[],
    key: string,
  ): Promise<Selection>;
  issues(id: string): Promise<Issue[]>;
}

export function liveConnectionApi(): ConnectionApi {
  const localPairing =
    import.meta.env.DEV && import.meta.env.GIGMATE_LOCAL_PAIRING === true;
  async function request<T>(path: string): Promise<T> {
    const response = await fetch(`/api/v1${path}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new ConnectionError(
        response.status === 401
          ? "UNAUTHENTICATED"
          : (result.error?.code ?? "HTTP_ERROR"),
        result.error?.message ?? "请求失败",
        result.request_id,
      );
    }
    return response.json() as Promise<T>;
  }
  async function pending(): Promise<never> {
    throw new ConnectionError(
      "CAPABILITY_PENDING",
      "扫码和会话授权功能待接入。当前可查看连接状态。",
    );
  }
  const base = (id: string) => `/connectors/${encodeURIComponent(id)}`;
  async function localRequest(id: string, kind: "status" | "qr") {
    const response = await fetch(
      `/__gigmate_local_pairing/${encodeURIComponent(id)}/${kind}`,
      {
        credentials: "same-origin",
        cache: "no-store",
        headers: { "X-GigMate-Local-Pairing": "1" },
      },
    );
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new ConnectionError(
        response.status === 401
          ? "UNAUTHENTICATED"
          : (result.error?.code ?? "LOCAL_PAIRING_UNAVAILABLE"),
        "无法读取本机扫码状态，请检查服务后刷新。",
      );
    }
    return response;
  }
  return {
    capabilities: { pairing: localPairing, start: false, selection: false },
    async connectors() {
      const result: Connector[] = [];
      let cursor: string | null = null;
      do {
        const page: Page<Connector> = await request(
          `/connectors?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        );
        result.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return result;
    },
    pairing: localPairing
      ? async (id) =>
          (await localRequest(id, "status")).json() as Promise<Pairing>
      : pending,
    start: pending,
    qr: localPairing
      ? async (id) => {
          const response = await localRequest(id, "qr");
          const blob = await response.blob();
          if (
            blob.type !== "image/png" ||
            blob.size === 0 ||
            blob.size > 2 * 1024 * 1024
          ) {
            throw new ConnectionError(
              "WAHA_INVALID_QR",
              "二维码图片无效，请刷新重试。",
            );
          }
          return blob;
        }
      : pending,
    selection: pending,
    chats: pending,
    save: pending,
    async issues(id) {
      const result: Issue[] = [];
      let cursor: string | null = null;
      do {
        const page: Page<Issue> = await request(
          `${base(id)}/recovery-issues?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        );
        result.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return result;
    },
  };
}

// Explicit, browser-only synthetic acceptance mode. No live credentials, QR or HTTP writes.
export function demoConnectionApi(): ConnectionApi & {
  connect(value: boolean): void;
  stale(): void;
} {
  const names = [
    "示例客户 · 摄影预约",
    "示例客户 · 网页设计",
    "示例项目讨论组",
  ];
  const choices: Choice[] = names.map((name, i) => ({
    choice_id: `demo-${i}`,
    token: `synthetic:${i}`,
    name,
    kind: i === 2 ? "group" : "direct",
    selected: false,
    conversation_id: null,
  }));
  let connected = false,
    stale = false,
    version = 1,
    selected: Choice[] = [];
  const health = {
    state: "healthy" as const,
    observed_at: "2026-10-06T08:00:00Z",
  };
  const connector = (): Connector => ({
    id: "00000000-0000-4000-8000-000000000099",
    connector: "waha",
    enabled: true,
    state: connected ? "connected" : "connecting",
    live_connected: connected && !stale,
    stale,
    observed_at: "2026-10-06T08:00:00Z",
    last_sync_at: null,
    accepted: 0,
    duplicates: 0,
    stale_events: 0,
    pending_jobs: 0,
    processing_jobs: 0,
    failed_jobs: 0,
    api_health: health,
    worker_health: health,
    monitor_health: health,
    provider_health: health,
    pipeline_ready: connected && !stale,
    review_required: stale,
    unresolved_issues: stale ? 1 : 0,
    metrics: {
      rejected: 0,
      retries: 0,
      lease_recoveries: 0,
      expired_leases: 0,
      oldest_pending_seconds: null,
      timed_jobs: 0,
      average_processing_ms: null,
      maximum_processing_ms: null,
      average_completion_latency_ms: null,
      last_error_code: null,
      last_rejection_at: null,
    },
  });
  const view = (): Selection => ({
    version,
    selected: selected.map((c) => ({ ...c, selected: true })),
  });
  return {
    capabilities: { pairing: true, start: true, selection: true },
    connect(value) {
      connected = value;
      stale = false;
    },
    stale() {
      stale = true;
    },
    async connectors() {
      return [connector()];
    },
    async pairing() {
      return {
        state: connected ? "WORKING" : "SCAN_QR_CODE",
        connected,
        qr_available: !connected,
      };
    },
    async start() {
      return this.pairing("");
    },
    async qr() {
      throw new ConnectionError("DEMO_QR", "演示模式不生成真实二维码");
    },
    async selection() {
      return view();
    },
    async chats() {
      return {
        items: choices.map((c) => ({
          ...c,
          selected: selected.some((s) => s.choice_id === c.choice_id),
        })),
        next_offset: null,
      };
    },
    async save(_id, value, next) {
      if (value.version !== version)
        throw new ConnectionError("VERSION_CONFLICT", "授权已更新，请重新查看");
      selected = next;
      version++;
      return view();
    },
    async issues() {
      return stale
        ? [
            {
              id: "00000000-0000-4000-8000-000000000098",
              connection_id: connector().id,
              code: "PROVIDER_UNAVAILABLE",
              started_at: "2026-10-06T08:00:00Z",
              last_seen_at: "2026-10-06T08:00:00Z",
              recovered_at: null,
              acknowledged_at: null,
              resolution: null,
              occurrences: 1,
            },
          ]
        : [];
    },
  };
}
