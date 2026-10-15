import type { components } from "./generated/api";

export type Connector = components["schemas"]["ConnectorStatus"];
export type Issue = components["schemas"]["RecoveryIssue"];
// View state derives from generated setup/choice contracts.
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
  retry(id: string): Promise<Discovery | void>;
  reconcile(id: string): Promise<void>;
  pause(id: string): Promise<void>;
  resume(id: string): Promise<void>;
  reviewIssues(id: string, issueIds: string[]): Promise<number>;
}

export { liveConnectionApi, clearConnectionAttempts } from "./waha-live-api";
