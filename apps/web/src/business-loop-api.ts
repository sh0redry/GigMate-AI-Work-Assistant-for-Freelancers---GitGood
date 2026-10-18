import { t } from "./i18n.ts";
import { sessionFetch } from "./read-cache.ts";
import { apiBase } from "./environment.ts";
import { workspaceApi, WorkspaceError } from "./workspace-api.ts";
import { loopReady, type Features } from "./features.ts";
import type { components } from "./generated/api";
export type Loop = components["schemas"];
export type LoopOrder = Loop["WorkOrder"];
export type LoopIntent = {
  path: string;
  method?: "POST" | "PUT";
  body: object;
  review: string;
};
type Saved = { key: string; intent: LoopIntent };
const routes = [
  /^\/work-orders\/[a-f0-9-]{36}\/(defer|requirements|archive|status|manual-field)$/i,
  /^\/work-orders\/[a-f0-9-]{36}\/requirements\/[a-f0-9-]{36}$/i,
  /^\/work-orders\/[a-f0-9-]{36}\/changes\/[a-f0-9-]{36}\/(confirm|reject)$/i,
  /^\/actions\/[a-f0-9-]{36}\/(edit|send|cancel)$/i,
  /^\/review-items\/[a-f0-9-]{36}\/assign$/i,
  /^\/settings\/schedule$/,
  /^\/tasks\/[a-f0-9-]{36}\/status$/i,
];
export function businessLoopApi(
  csrf: string,
  account: string,
  features: Features,
  fetcher = fetch,
  supplied?: Storage,
) {
  const cachedFetch = (url: string, options: RequestInit) =>
    sessionFetch(url, options, fetcher);
  const read = workspaceApi(csrf, fetcher),
    name = `gigmate-loop-attempt:${apiBase()}:${account}`;
  let storage: Storage | undefined,
    pending: Saved | null = null,
    storageError = "",
    busy = false;
  function valid(value: Saved) {
    return (
      value &&
      /^[a-f0-9-]{36}$/i.test(value.key) &&
      value.intent &&
      routes.some((r) => r.test(value.intent.path)) &&
      typeof value.intent.review === "string" &&
      value.intent.body &&
      [undefined, "POST", "PUT"].includes(value.intent.method)
    );
  }
  try {
    storage = supplied ?? globalThis.sessionStorage;
    const raw = storage.getItem(name);
    if (raw) {
      const value = JSON.parse(raw);
      if (!valid(value)) throw Error();
      pending = value;
    }
  } catch {
    storageError = t("无法安全保存原操作，请恢复浏览器存储后再操作。");
  }
  function gate(path: string) {
    if (
      !loopReady(features) ||
      (!features.business_sending &&
        /^\/actions\/.*\/(send|cancel)$/.test(path)) ||
      (!features.manual_assignment && /^\/review-items\//.test(path))
    )
      throw new WorkspaceError(
        "FEATURE_UNAVAILABLE",
        t("当前后端版本未提供此功能。"),
      );
  }
  function check() {
    try {
      if (
        storageError ||
        !storage ||
        storage.getItem(name) !== (pending ? JSON.stringify(pending) : null)
      )
        throw new WorkspaceError(
          "UNRESOLVED_ATTEMPT",
          storageError || t("原记录已变化，请重新打开并核对。"),
        );
    } catch (e) {
      if (e instanceof WorkspaceError) throw e;
      throw new WorkspaceError(
        "ATTEMPT_STORAGE_UNAVAILABLE",
        t("无法读取原操作记录，本次未提交。"),
      );
    }
  }
  async function dispatch(retry = false) {
    check();
    const saved = pending!;
    gate(saved.intent.path);
    busy = true;
    try {
      if (retry && saved.intent.method === "PUT") {
        const current = await read<{ data: Loop["ScheduleSettings"] }>(
          "/settings/schedule",
        );
        const command = saved.intent
          .body as Loop["UpdateScheduleSettingsCommand"];
        const { version, ...actual } = current.data;
        const { version: ignored, ...target } = command.settings;
        const canonical = (v: object) =>
          JSON.stringify(
            Object.entries(v).sort(([a], [b]) => a.localeCompare(b)),
          );
        if (
          version !== command.expected_version + 1 ||
          canonical(actual) !== canonical(target)
        )
          throw new WorkspaceError(
            "RESULT_UNKNOWN",
            t(
              "工作时间保存结果仍无法核对；保留原记录，联系维护者核查，不自动重写。",
            ),
          );
        check();
        storage!.removeItem(name);
        pending = null;
        return current.data;
      }
      const response = await cachedFetch(apiBase() + saved.intent.path, {
        method: saved.intent.method ?? "POST",
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          "Idempotency-Key": saved.key,
        },
        body: JSON.stringify(saved.intent.body),
      });
      const value = await response.json().catch(() => null);
      if (
        !retry &&
        [400, 403, 404, 409, 422].includes(response.status) &&
        [
          "VALIDATION_FAILED",
          "VERSION_CONFLICT",
          "APPROVAL_STALE",
          "NOT_FOUND",
          "SCHEDULE_CONFLICT",
          "CHECKLIST_OPEN",
          "DEPENDENCY_OPEN",
          "MODEL_OUTCOME_UNKNOWN",
          "CONSENT_REVOKED",
          "SEND_NOT_AUTHORIZED",
          "SEND_CHAT_NOT_LINKED",
          "SEND_REQUEST_KEY_TAKEN",
        ].includes(value?.error?.code)
      ) {
        check();
        storage!.removeItem(name);
        pending = null;
      }
      if (!response.ok || !value?.data)
        throw new WorkspaceError(
          response.status === 401
            ? "UNAUTHENTICATED"
            : (value?.error?.code ?? "RESULT_UNKNOWN"),
          pending
            ? t(
                "操作尚未核对完成，原记录保留；请读取当前状态后明确核对原请求。",
              )
            : value?.error?.code === "CHECKLIST_OPEN"
              ? t("仍有未完成检查项。请先处理，或明确核对后确认仍要结束工单。")
              : value?.error?.code === "DEPENDENCY_OPEN"
                ? t("前置待办尚未完成，请先处理依赖事项。")
                : t(
                    "后端已明确拒绝本次操作，没有保存。请刷新并核对条件后重新操作。",
                  ),
        );
      const data = value.data;
      if (
        typeof data !== "object" ||
        Array.isArray(data) ||
        (data.account_id && data.account_id !== account)
      )
        throw new WorkspaceError(
          "RESULT_UNKNOWN",
          t("结果归属无法核对，原记录保留。"),
        );
      const parts = saved.intent.path.split("/");
      const expected = saved.intent.body as { expected_version?: number };
      const validScope =
        parts[1] === "work-orders"
          ? data.account_id === account &&
            data.id === parts[2] &&
            Number.isInteger(data.version) &&
            data.version === (expected.expected_version ?? -1) + 1
          : parts[1] === "actions"
            ? data.account_id === account &&
              data.id === parts[2] &&
              Number.isInteger(data.revision)
            : parts[1] === "review-items"
              ? data.job_id === parts[2] &&
                data.conversation_id &&
                data.action === (saved.intent.body as { action: string }).action
              : parts[1] === "tasks"
                ? data.account_id === account &&
                  data.id === parts[2] &&
                  data.work_order_version ===
                    (expected.expected_version ?? -1) + 1 &&
                  data.state === (saved.intent.body as { state: string }).state
                : Number.isInteger(data.version) &&
                  data.version === (expected.expected_version ?? -1) + 1;
      if (!validScope)
        throw new WorkspaceError(
          "RESULT_UNKNOWN",
          t("响应与原操作的归属或版本不符，原记录保留。"),
        );
      check();
      storage!.removeItem(name);
      pending = null;
      return data;
    } catch (e) {
      if (e instanceof WorkspaceError) throw e;
      throw new WorkspaceError(
        "RESULT_UNKNOWN",
        t("连接中断，原内容与编号已保留，没有自动重发。"),
      );
    } finally {
      busy = false;
    }
  }
  return {
    get pending() {
      return pending;
    },
    get error() {
      return storageError;
    },
    async read<T>(path: string, signal?: AbortSignal): Promise<T> {
      gate(path);
      return (await read<{ data: T }>(path, undefined, signal)).data;
    },
    async submit(intent: LoopIntent) {
      gate(intent.path);
      check();
      if (pending || busy)
        throw new WorkspaceError("UNRESOLVED_ATTEMPT", t("先核对已有原操作。"));
      const saved = {
        key: crypto.randomUUID(),
        intent: structuredClone(intent),
      };
      if (!valid(saved))
        throw new WorkspaceError("VALIDATION_FAILED", t("操作内容无效。"));
      try {
        storage!.setItem(name, JSON.stringify(saved));
        pending = saved;
      } catch {
        throw new WorkspaceError(
          "ATTEMPT_STORAGE_UNAVAILABLE",
          t("本次未提交，无法保存原操作。"),
        );
      }
      return dispatch();
    },
    async retry() {
      if (!pending || busy)
        throw new WorkspaceError(
          "UNRESOLVED_ATTEMPT",
          t("没有可核对的原请求。"),
        );
      return dispatch(true);
    },
  };
}
export type LoopApi = ReturnType<typeof businessLoopApi>;
