import { apiBase } from "./environment.ts";
import { t } from "./i18n.ts";
import type { components } from "./generated/api";
import { WorkspaceError } from "./workspace-api";

export type AssistantTurn = components["schemas"]["AssistantTurnView"];
export type AssistantDraft = components["schemas"]["AssistantDraftView"];
export type AssistantCapabilities =
  components["schemas"]["AssistantCapabilities"];
export type AssistantContext = components["schemas"]["AssistantContext"];
export type SourceRef = components["schemas"]["SourceRef"];

export const FINAL_STATES = new Set([
  "completed",
  "failed",
  "unknown",
  "superseded",
]);

const messages = (): Record<string, string> => ({
  UNAUTHENTICATED: t("登录已过期，请重新登录。"),
  ASSISTANT_DISABLED: t("助手已关闭，请联系维护者开启。"),
  ASSISTANT_BUDGET_EXCEEDED: t("今天的提问次数已用完，请明天再试。"),
  ASSISTANT_CONTEXT_STALE: t("聊天或工单刚刚有更新，请刷新后再问。"),
  ASSISTANT_SELECTION_MISMATCH: t("所选工单不属于这个聊天，请重新选择。"),
  ASSISTANT_SOURCE_STALE: t("所选客户消息已变化，请重新选择。"),
  ASSISTANT_DRAFT_NOT_USABLE: t("这份草稿已失效或已采用，不能再放入输入框。"),
  CONSENT_REVOKED: t("当前处理授权已暂停，请联系接入负责人核对。"),
  IDEMPOTENCY_CONFLICT: t("这次提问的记录与内容不一致，请重新提问。"),
  NOT_FOUND: t("当前聊天、工单或记录不可用，请刷新。"),
});

/** Assistant calls. A question keeps one Idempotency-Key, so a retry after an
 * unknown network outcome returns the original turn instead of asking twice. */
export function assistantApi(csrf: string, fetcher: typeof fetch = fetch) {
  const base = apiBase();
  async function call<T>(
    path: string,
    init: { body?: unknown; key?: string; signal?: AbortSignal } = {},
  ): Promise<T> {
    const post = init.body !== undefined || init.key !== undefined;
    let response: Response;
    try {
      response = await fetcher(`${base}${path}`, {
        method: post ? "POST" : "GET",
        credentials: "same-origin",
        cache: "no-store",
        signal: init.signal,
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          ...(init.key ? { "Idempotency-Key": init.key } : {}),
        },
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
      });
    } catch (error) {
      if (init.signal?.aborted)
        throw new DOMException("Cancelled", "AbortError");
      throw new WorkspaceError(
        post ? "RESULT_UNKNOWN" : "UNAVAILABLE",
        post
          ? t("暂时无法确认是否已提交。可以点“核对”，不会重复提问。")
          : t("暂时无法连接本地服务，请检查服务后刷新。"),
      );
    }
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      const code =
        response.status === 401
          ? "UNAUTHENTICATED"
          : (result?.error?.code ?? `HTTP_${response.status}`);
      throw new WorkspaceError(
        code,
        messages()[code] ??
          t("操作未能完成或结果暂无法确认，请刷新核对后再操作。"),
      );
    }
    if (!result || typeof result !== "object" || !("data" in result))
      throw new WorkspaceError(
        "INVALID_RESPONSE",
        t("服务响应无效，请刷新核对当前状态。"),
      );
    return result.data as T;
  }
  return {
    capabilities: (signal?: AbortSignal) =>
      call<AssistantCapabilities>("/assistant/capabilities", { signal }),
    conversationVersion: async (conversation: string, signal?: AbortSignal) =>
      (
        await call<{ context_version: number }>(
          `/conversations/${encodeURIComponent(conversation)}`,
          { signal },
        )
      ).context_version,
    ask: (
      body: {
        question: string;
        thread_id?: string | null;
        context?: AssistantContext;
      },
      key: string,
      signal?: AbortSignal,
    ) => call<AssistantTurn>("/assistant/turns", { body, key, signal }),
    turn: (id: string, signal?: AbortSignal) =>
      call<AssistantTurn>(`/assistant/turns/${encodeURIComponent(id)}`, {
        signal,
      }),
    draft: (id: string, signal?: AbortSignal) =>
      call<AssistantDraft>(`/assistant/drafts/${encodeURIComponent(id)}`, {
        signal,
      }),
    consume: (id: string, signal?: AbortSignal) =>
      call<AssistantDraft>(
        `/assistant/drafts/${encodeURIComponent(id)}/consume`,
        { body: {}, signal },
      ),
  };
}
