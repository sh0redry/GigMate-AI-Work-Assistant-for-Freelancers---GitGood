import { ConnectionError } from "./connection-api";
import type { components } from "./generated/api";

export type Attachment = components["schemas"]["WahaAttachmentView"];
export type MediaJob = components["schemas"]["WahaMediaJobView"];
type Command = components["schemas"]["WahaMediaCommand"];
type Capabilities = components["schemas"]["WahaMediaCapabilities"];

export function mediaApi(connection: string, csrf: string) {
  const base = `/api/v1/connectors/${encodeURIComponent(connection)}`;
  const attempts = new Map<string, Command>();
  async function response(path: string, body?: object, key?: string) {
    let value: Response;
    try {
      value = await fetch(base + path, {
        method: body ? "POST" : "GET",
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
        body ? "MEDIA_REQUEST_UNKNOWN" : "NETWORK_ERROR",
        "请求未能确认，请刷新核对；不要另建模型请求。 ",
      );
    }
    if (!value.ok) {
      const data = await value.json().catch(() => ({}));
      throw new ConnectionError(
        body && value.status >= 500
          ? "MEDIA_REQUEST_UNKNOWN"
          : value.status === 404 && path === "/media/capabilities"
            ? "MEDIA_API_NOT_INSTALLED"
            : value.status === 401
              ? "UNAUTHENTICATED"
              : (data.error?.code ?? "MEDIA_UNAVAILABLE"),
        "附件暂不可用，请核对授权、来源和处理状态。",
      );
    }
    return value;
  }
  async function detail<T>(
    path: string,
    body?: object,
    key?: string,
  ): Promise<T> {
    try {
      return (await (await response(path, body, key)).json()).data;
    } catch (error) {
      if (error instanceof ConnectionError) throw error;
      throw new ConnectionError(
        body ? "MEDIA_REQUEST_UNKNOWN" : "INVALID_RESPONSE",
        "响应未能完整读取，请核对已有任务。",
      );
    }
  }
  const setup = () => detail<components["schemas"]["WahaSetup"]>("/setup");
  return {
    downloadUrl: (id: string) =>
      `${base}/media/attachments/${encodeURIComponent(id)}/content?download=true`,
    capabilities: () => detail<Capabilities>("/media/capabilities"),
    async find(snapshot: string): Promise<Attachment | null> {
      const page = await (
        await response(
          `/media/attachments?snapshot_id=${encodeURIComponent(snapshot)}`,
        )
      ).json();
      return page.items[0] ?? null;
    },
    attachment: (id: string) =>
      detail<Attachment>(`/media/attachments/${encodeURIComponent(id)}`),
    job: (id: string) =>
      detail<MediaJob>(`/media/jobs/${encodeURIComponent(id)}`),
    async start(input: Omit<Command, "expected_version">, key: string) {
      let command = attempts.get(key);
      if (!command) {
        command = {
          ...input,
          expected_version: (await setup()).control_version,
        };
        attempts.set(key, command);
      } else if (
        JSON.stringify({ ...command, expected_version: undefined }) !==
        JSON.stringify(input)
      ) {
        throw new ConnectionError(
          "IDEMPOTENCY_CONFLICT",
          "请保留原读取范围与同意选项核对原请求。",
        );
      }
      const job = await detail<MediaJob>("/media/jobs", command, key);
      if (
        !job ||
        typeof job.id !== "string" ||
        typeof job.attachment_id !== "string" ||
        ![
          "pending",
          "running",
          "retry_wait",
          "succeeded",
          "failed",
          "cancelled",
          "result_unknown",
        ].includes(job.state)
      )
        throw new ConnectionError(
          "MEDIA_REQUEST_UNKNOWN",
          "任务响应无效，请保留原请求核对。",
        );
      return job;
    },
    async cancel(id: string) {
      return detail<MediaJob>(`/media/jobs/${encodeURIComponent(id)}/cancel`, {
        expected_version: (await setup()).control_version,
      });
    },
    async reconcile(id: string) {
      return detail<MediaJob>(
        `/media/jobs/${encodeURIComponent(id)}/reconcile`,
        { expected_version: (await setup()).control_version },
      );
    },
    async preview(id: string) {
      return (
        await response(`/media/attachments/${encodeURIComponent(id)}/content`)
      ).blob();
    },
    evidence(asset: Attachment) {
      if (!asset.result_job_id || !asset.reviewed_at)
        throw new ConnectionError(
          "MEDIA_REVIEW_REQUIRED",
          "请先核对当前结果来源。",
        );
      const query = new URLSearchParams({
        expected_attachment_version: String(asset.version),
        expected_context_version: String(asset.context_version),
        expected_result_job_id: asset.result_job_id,
      });
      return detail<components["schemas"]["WahaMediaEvidence"]>(
        `/media/attachments/${encodeURIComponent(asset.id)}/evidence?${query}`,
      );
    },
    async review(asset: Attachment, note: string) {
      return detail<Attachment>(
        `/media/attachments/${encodeURIComponent(asset.id)}/review`,
        {
          expected_attachment_version: asset.version,
          expected_context_version: asset.context_version,
          expected_result_job_id: asset.result_job_id,
          reviewed: true,
          note,
        },
      );
    },
  };
}
