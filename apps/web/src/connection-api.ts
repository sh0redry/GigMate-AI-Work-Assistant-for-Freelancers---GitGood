import type { components } from "./generated/api";

export type Connector = components["schemas"]["ConnectorStatus"];
export type Issue = components["schemas"]["RecoveryIssue"];
// View state derives from generated setup/choice contracts; demo never writes.
export type Pairing = {
  enabled: boolean;
  control_version: number;
  state: string;
  connected: boolean;
  qr_available: boolean;
  available: boolean;
  provider_sample_stale: boolean;
  operation_id: string | null;
  operation_state: components["schemas"]["WahaControlResult"]["state"] | null;
  operation_action: components["schemas"]["WahaControlResult"]["action"] | null;
  operation_error: string | null;
  retry_available: boolean;
};
export type Choice = components["schemas"]["WahaChoice"];
export type Selection = {
  control_version: number;
  selected: Choice[];
  choices: Choice[];
};
export type Discovery = { items: Choice[]; next_offset: number | null };

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
    recovery: boolean;
  };
  connectors(): Promise<Connector[]>;
  pairing(id: string, force?: boolean): Promise<Pairing>;
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
  restart(id: string, key: string): Promise<void>;
  retry(id: string): Promise<void>;
  reconcile(id: string): Promise<void>;
  pause(id: string): Promise<void>;
  resume(id: string): Promise<void>;
  reviewIssues(id: string, issueIds: string[]): Promise<number>;
}

export { liveConnectionApi, clearConnectionAttempts } from "./waha-live-api";

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
    id: `demo-${i}`,
    expires_at: null,
    label: name,
    selected: false,
  }));
  let connected = false,
    enabled = true,
    stale = false,
    failed = false,
    reviewed = false,
    version = 1,
    selected: Choice[] = [];
  const health = {
    state: "healthy" as const,
    observed_at: "2026-10-06T08:00:00Z",
  };
  const connector = (): Connector => ({
    id: "00000000-0000-4000-8000-000000000099",
    connector: "waha",
    enabled,
    state: connected ? "connected" : "connecting",
    live_connected: enabled && connected && !stale,
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
    pipeline_ready: enabled && connected && !stale,
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
    control_version: version,
    choices: choices.map((c) => ({
      ...c,
      selected: selected.some((x) => x.id === c.id),
    })),
    selected: selected.map((c) => ({ ...c, selected: true })),
  });
  return {
    capabilities: {
      pairing: true,
      start: true,
      selection: true,
      recovery: true,
    },
    connect(value) {
      connected = value;
      stale = false;
      failed = !value;
    },
    stale() {
      stale = true;
    },
    async connectors() {
      return [connector()];
    },
    async pairing() {
      return {
        enabled,
        control_version: version,
        state: connected ? "WORKING" : failed ? "FAILED" : "SCAN_QR_CODE",
        connected: enabled && connected,
        available: true,
        provider_sample_stale: false,
        operation_id: null,
        operation_state: null,
        operation_action: null,
        operation_error: null,
        retry_available: false,
        qr_available: enabled && !connected && !failed,
      };
    },
    async restart() {
      failed = false;
      stale = false;
    },
    async reconcile() {},
    async retry() {},
    async pause() {
      enabled = false;
      version++;
    },
    async resume() {
      enabled = true;
      version++;
    },
    async reviewIssues(_id, ids) {
      reviewed = true;
      return ids.length;
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
          selected: selected.some((s) => s.id === c.id),
        })),
        next_offset: null,
      };
    },
    async save(_id, value, next) {
      if (value.control_version !== version)
        throw new ConnectionError("VERSION_CONFLICT", "授权已更新，请重新查看");
      selected = next;
      version++;
      return view();
    },
    async issues() {
      return [
        ...(!reviewed
          ? [
              {
                id: "00000000-0000-4000-8000-000000000097",
                connection_id: connector().id,
                code: "MONITOR_GAP",
                started_at: "2026-10-06T07:00:00Z",
                last_seen_at: "2026-10-06T07:05:00Z",
                recovered_at: "2026-10-06T07:05:00Z",
                acknowledged_at: null,
                resolution: null,
                occurrences: 1,
              },
            ]
          : []),
        ...(stale || failed
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
          : []),
      ];
    },
  };
}
