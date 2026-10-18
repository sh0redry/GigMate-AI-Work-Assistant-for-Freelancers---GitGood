import { t } from "./i18n.ts";
import { sessionFetch } from "./read-cache";
import { ConnectionError, type Choice, type Connector } from "./connection-api";
import { apiBase } from "./environment";
import type { TimelineMessage } from "./waha-sync-api";
import type { Order } from "./workspace-api";
import type { components } from "./generated/api";
import { orderedMessages } from "./conversation-view";

export type AgentDraft = components["schemas"]["AgentDraftView"];
type Page<T> = { items: T[]; next_cursor: string | null };
export const MAX_CONVERSATION_PAGES = 10;

export function conversationApi(csrf: string, fetcher: typeof fetch = fetch) {
  async function request<T>(
    path: string,
    signal?: AbortSignal,
    body?: object,
  ): Promise<T> {
    let response: Response;
    try {
      response = await sessionFetch(
        apiBase() + path,
        {
          credentials: "same-origin",
          cache: "no-store",
          signal: signal
            ? AbortSignal.any([signal, AbortSignal.timeout(10000)])
            : AbortSignal.timeout(10000),
          method: body ? "POST" : "GET",
          headers: body
            ? { "Content-Type": "application/json", "X-CSRF-Token": csrf }
            : {},
          body: body ? JSON.stringify(body) : undefined,
        },
        fetcher,
      );
    } catch {
      if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
      throw new ConnectionError(
        body ? "DRAFT_RESULT_UNKNOWN" : "NETWORK_ERROR",
        t("会话请求未完成，请恢复连接后核对原记录。"),
      );
    }
    const result = await response.json().catch(() => null);
    if (!response.ok || !result) {
      const code =
        response.status === 401
          ? "UNAUTHENTICATED"
          : response.status === 403
            ? "FORBIDDEN"
            : response.status === 404
              ? "CONVERSATION_API_UNAVAILABLE"
              : response.status >= 500 ||
                  response.status === 429 ||
                  response.status === 408
                ? body
                  ? "DRAFT_RESULT_UNKNOWN"
                  : "UNAVAILABLE"
                : (result?.error?.code ?? "INVALID_RESPONSE");
      throw new ConnectionError(
        code,
        code === "CONVERSATION_API_UNAVAILABLE"
          ? t("当前后端尚未提供此会话功能，请联系维护者升级。")
          : t("会话请求未完成，请恢复连接后核对原记录。"),
      );
    }
    return result;
  }
  function checkedPage<T>(value: Page<T>): Page<T> {
    if (
      !value ||
      !Array.isArray(value.items) ||
      !(value.next_cursor === null || typeof value.next_cursor === "string")
    )
      throw new ConnectionError(
        "INVALID_RESPONSE",
        t("会话范围或分页响应无效，已停止显示。"),
      );
    return value;
  }
  async function bounded<T>(path: string, signal?: AbortSignal) {
    const items: T[] = [];
    const cursors = new Set<string>();
    let cursor: string | null = null;
    for (let count = 0; count < MAX_CONVERSATION_PAGES; count++) {
      const page: Page<T> = checkedPage(
        await request<Page<T>>(
          `${path}?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
          signal,
        ),
      );
      items.push(...page.items);
      cursor = page.next_cursor;
      if (!cursor) return { items, partial: false };
      if (cursors.has(cursor))
        throw new ConnectionError(
          "INVALID_RESPONSE",
          t("会话范围或分页响应无效，已停止显示。"),
        );
      cursors.add(cursor);
    }
    return { items, partial: true };
  }
  return {
    async connectors(signal?: AbortSignal) {
      return bounded<Connector>("/connectors", signal);
    },
    async chats(connection: string, signal?: AbortSignal) {
      const value = await request<{ data: Choice[] }>(
        `/connectors/${encodeURIComponent(connection)}/chats`,
        signal,
      );
      if (!Array.isArray(value.data))
        throw new ConnectionError(
          "INVALID_RESPONSE",
          t("会话范围或分页响应无效，已停止显示。"),
        );
      return value.data.filter((chat) => chat.selected === true);
    },
    async timeline(
      connection: string,
      chat: Choice,
      pages: number,
      anchor?: string,
      signal?: AbortSignal,
    ) {
      const items: TimelineMessage[] = [];
      const cursors = new Set<string>();
      let cursor: string | null = null;
      let count = 0;
      let found = !anchor;
      for (; count < MAX_CONVERSATION_PAGES; count++) {
        const page: Page<TimelineMessage> = checkedPage(
          await request<Page<TimelineMessage>>(
            `/connectors/${encodeURIComponent(connection)}/chats/${encodeURIComponent(chat.id)}/timeline?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
            signal,
          ),
        );
        if (
          page.items.some(
            (m) =>
              m.chat_id !== chat.id ||
              (chat.conversation_id &&
                m.conversation_id !== chat.conversation_id) ||
              !m.conversation_id ||
              !m.id ||
              !Number.isFinite(Date.parse(m.occurred_at)),
          )
        )
          throw new ConnectionError(
            "INVALID_RESPONSE",
            t("会话范围或分页响应无效，已停止显示。"),
          );
        items.push(...page.items);
        if (anchor && page.items.some((m) => m.id === anchor)) found = true;
        cursor = page.next_cursor;
        if (!cursor || (count + 1 >= pages && found)) {
          count++;
          break;
        }
        if (cursors.has(cursor))
          throw new ConnectionError(
            "INVALID_RESPONSE",
            t("会话范围或分页响应无效，已停止显示。"),
          );
        cursors.add(cursor);
      }
      if (new Set(items.map((m) => m.conversation_id)).size > 1)
        throw new ConnectionError(
          "INVALID_RESPONSE",
          t("会话范围或分页响应无效，已停止显示。"),
        );
      return {
        items: orderedMessages(items),
        cursor,
        pages: count,
        truncated: !!anchor && !found && !!cursor,
      };
    },
    orders: (signal?: AbortSignal) => bounded<Order>("/work-orders", signal),
    async drafts(order: Order, conversation: string, signal?: AbortSignal) {
      const result = await bounded<AgentDraft>(
        `/work-orders/${encodeURIComponent(order.id)}/drafts`,
        signal,
      );
      if (result.items.some((d) => d.work_order_id !== order.id))
        throw new ConnectionError(
          "INVALID_RESPONSE",
          t("会话范围或分页响应无效，已停止显示。"),
        );
      return {
        ...result,
        items: result.items.filter((d) => d.conversation_id === conversation),
      };
    },
    async consume(draft: AgentDraft, signal?: AbortSignal) {
      const value = await request<{ data: AgentDraft }>(
        `/drafts/${encodeURIComponent(draft.id)}/consume`,
        signal,
        {},
      );
      if (
        !value.data ||
        value.data.id !== draft.id ||
        value.data.work_order_id !== draft.work_order_id ||
        value.data.conversation_id !== draft.conversation_id ||
        value.data.status !== "consumed" ||
        value.data.execution_authority !== false ||
        value.data.text !== draft.text ||
        value.data.context_version !== draft.context_version ||
        value.data.base_work_order_version !== draft.base_work_order_version ||
        value.data.proposal_id !== draft.proposal_id
      )
        throw new ConnectionError(
          "DRAFT_RESULT_UNKNOWN",
          t("会话范围或分页响应无效，已停止显示。"),
        );
      return value.data;
    },
  };
}
