import { t } from "./i18n.ts";
import { sessionFetch } from "./read-cache.ts";
import type { OrderCommands } from "./order-command-api";
import { apiBase } from "./environment.ts";
import type { components } from "./generated/api";

export type Order = components["schemas"]["WorkOrder"];
export type Change = components["schemas"]["ChangeView"];
export type Message = components["schemas"]["ConversationMessage"];
export type Task = components["schemas"]["Task"];
export type Calendar = components["schemas"]["CalendarEvent"];
export type Login = components["schemas"]["LoginResult"];
export type Detail<T> = { data: T };
type Page<T> = { items: T[]; next_cursor: string | null };
export type RequestApi = <T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
) => Promise<T>;

export class WorkspaceError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export function workspaceApi(
  csrf = "",
  fetcher: typeof fetch = fetch,
): RequestApi {
  const cachedFetch = (url: string, options: RequestInit) =>
    sessionFetch(url, options, fetcher);
  const base = apiBase();
  return async <T>(
    path: string,
    body?: unknown,
    signal?: AbortSignal,
  ): Promise<T> => {
    const timeout = AbortSignal.timeout(10000);
    let response: Response;
    let result;
    try {
      response = await cachedFetch(`${base}${path}`, {
        method: body === undefined ? "GET" : "POST",
        credentials: "same-origin",
        cache: "no-store",
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          ...(body === undefined
            ? {}
            : { "Idempotency-Key": crypto.randomUUID() }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      result = await response.json().catch(() => null);
    } catch (error) {
      if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
      if ((error as { name?: string })?.name === "AbortError")
        throw new WorkspaceError(
          "READ_INVALIDATED",
          t("读取期间登录、授权或数据发生变化，请刷新并核对会话授权。"),
        );
      throw new WorkspaceError(
        "UNAVAILABLE",
        body === undefined
          ? t("暂时无法连接本地服务，请检查服务后刷新。")
          : t("暂时无法确认操作结果。请恢复服务并刷新核对，避免反复提交。"),
      );
    }
    if (!response.ok) {
      const code =
        response.status === 401
          ? "UNAUTHENTICATED"
          : response.status === 403
            ? (result?.error?.code ?? "FORBIDDEN")
            : response.status === 404
              ? (result?.error?.code ?? "NOT_FOUND")
              : (result?.error?.code ?? "UNAVAILABLE");
      const messages: Record<string, string> = {
        UNAUTHENTICATED:
          path === "/auth/login"
            ? t("账号或密码不正确，请重新输入。")
            : t("登录已过期，请重新登录。"),
        VERSION_CONFLICT: t("业务或消息已更新，请刷新并重新核对当前提议。"),
        APPROVAL_STALE: t("来源消息已变化，请刷新并重新核对。"),
        SCHEDULE_CONFLICT: t("该时段与其他预约冲突，不能确认，请刷新查看。"),
        CONSENT_REVOKED: t("当前处理授权已暂停，请联系接入负责人核对。"),
        CSRF_REJECTED:
          path === "/auth/login"
            ? t("当前环境尚未允许此网页地址登录，请联系负责配置的队友确认。")
            : t("登录验证已变化，请退出后重新登录。"),
        NOT_FOUND: t("当前工单或会话不可用，请刷新并检查当前账号和会话授权。"),
      };
      throw new WorkspaceError(
        code,
        messages[code] ??
          (body === undefined
            ? t("暂时无法读取数据，请检查本地服务后刷新。")
            : t("操作未能完成或结果暂无法确认，请刷新核对后再操作。")),
      );
    }
    if (result === null)
      throw new WorkspaceError(
        "INVALID_RESPONSE",
        t("服务响应无效，请刷新核对当前状态。"),
      );
    return result as T;
  };
}

export async function allPages<T>(
  api: RequestApi,
  path: string,
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  do {
    const page: Page<T> = await api(
      `${path}${path.includes("?") ? "&" : "?"}limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      undefined,
      signal,
    );
    if (
      !page ||
      !Array.isArray(page.items) ||
      (page.next_cursor !== null && typeof page.next_cursor !== "string")
    ) {
      throw new WorkspaceError(
        "INVALID_RESPONSE",
        t("列表数据无效，请刷新重试。"),
      );
    }
    items.push(...page.items);
    cursor = page.next_cursor;
    if (cursor && seen.has(cursor))
      throw new WorkspaceError(
        "INVALID_RESPONSE",
        t("分页数据未能完整读取，请刷新重试。"),
      );
    if (cursor) seen.add(cursor);
  } while (cursor);
  return items;
}

export type BusinessSnapshot = {
  orders: Order[];
  tasks: Task[];
  calendar: Calendar[];
  selected: string;
  changes: Change[];
  messages: Message[];
  contextVersion: number;
  contexts?: Record<string, number>;
};
export type BusinessApi = {
  load(selected: string, signal: AbortSignal): Promise<BusinessSnapshot>;
  confirm(snapshot: BusinessSnapshot, change: Change): Promise<void>;
};

export function businessApi(
  request: RequestApi,
  commands?: OrderCommands,
): BusinessApi {
  return {
    async load(selected, signal) {
      const [orders, tasks, calendar] = await Promise.all([
        allPages<Order>(request, "/work-orders", signal),
        allPages<Task>(request, "/tasks", signal),
        allPages<Calendar>(request, "/calendar-events", signal),
      ]);
      const order = orders.find((o) => o.id === selected) ?? orders[0];
      const conversation = order?.conversation_ids[0];
      if (!order)
        return {
          orders,
          tasks,
          calendar,
          selected: "",
          changes: [],
          messages: [],
          contextVersion: 0,
        };
      if (!conversation)
        throw new WorkspaceError(
          "NO_CONVERSATION",
          t("当前工单没有可核对的对话，请联系后端负责人。"),
        );
      const [changes, timelines] = await Promise.all([
        allPages<Change>(request, `/work-orders/${order.id}/changes`, signal),
        Promise.all(
          [...new Set(order.conversation_ids)].map(async (id) => {
            const [messages, info] = await Promise.all([
              allPages<Message>(
                request,
                `/conversations/${id}/messages`,
                signal,
              ),
              request<Detail<components["schemas"]["Conversation"]>>(
                `/conversations/${id}`,
                undefined,
                signal,
              ),
            ]);
            if (
              info.data.id !== id ||
              !Number.isInteger(info.data.context_version) ||
              info.data.context_version < 0 ||
              messages.some((message) => message.conversation_id !== id)
            )
              throw new WorkspaceError(
                "INVALID_RESPONSE",
                t("对话范围或版本无效，请刷新核对。"),
              );
            return { id, messages, version: info.data.context_version };
          }),
        ),
      ]);
      return {
        orders,
        tasks,
        calendar,
        selected: order.id,
        changes,
        messages: timelines
          .flatMap((t) => t.messages)
          .sort(
            (a, b) =>
              a.occurred_at.localeCompare(b.occurred_at) ||
              a.id.localeCompare(b.id) ||
              a.revision - b.revision,
          ),
        contextVersion: timelines[0].version,
        contexts: Object.fromEntries(timelines.map((t) => [t.id, t.version])),
      };
    },
    async confirm(snapshot, change) {
      const order = snapshot.orders.find((o) => o.id === snapshot.selected);
      if (!order || order.id !== change.work_order_id)
        throw new WorkspaceError(
          "VERSION_CONFLICT",
          t("业务已切换，请刷新并重新核对。"),
        );
      const context = changeContext(snapshot, change);
      if (!["schedule", "address"].includes(change.field))
        throw new WorkspaceError(
          "VALIDATION_FAILED",
          t("当前只能确认时间或地址提议。"),
        );
      if (context === null)
        throw new WorkspaceError(
          "APPROVAL_STALE",
          t("来源对话或消息版本无法核对，请刷新并重新审核。"),
        );
      const body = {
        expected_version: order.version,
        expected_context_version: context,
        apply_calendar_update: change.field === "schedule",
      };
      if (commands)
        await commands.submit({
          kind: "confirm",
          orderId: order.id,
          changeId: change.id,
          review: {
            field: change.field as "schedule" | "address",
            summary: order.summary,
            oldValue: change.old_value,
            newValue: change.new_value,
            sources: change.sources,
          },
          body,
        });
      else
        await request(
          `/work-orders/${order.id}/changes/${change.id}/confirm`,
          body,
        );
    },
  };
}

// ChangeView does not expose conversation_id. Resolve it only from exact canonical
// source revisions; never guess the first linked conversation for a multi-chat order.
export function changeContext(
  snapshot: BusinessSnapshot,
  change: Change,
): number | null {
  if (!snapshot.contexts) return snapshot.contextVersion; // legacy single-chat snapshots
  const ids = new Set<string>();
  for (const source of change.sources) {
    const message = snapshot.messages.find(
      (m) =>
        m.id === source.message_id &&
        m.revision === source.message_revision &&
        !m.revoked,
    );
    if (!message) return null;
    ids.add(message.conversation_id);
  }
  if (ids.size !== 1) return null;
  return snapshot.contexts[[...ids][0]] ?? null;
}
