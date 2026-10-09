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
  return async <T>(
    path: string,
    body?: unknown,
    signal?: AbortSignal,
  ): Promise<T> => {
    const timeout = AbortSignal.timeout(10000);
    let response: Response;
    let result;
    try {
      response = await fetcher(`/api/v1${path}`, {
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
    } catch {
      if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
      throw new WorkspaceError(
        "UNAVAILABLE",
        body === undefined
          ? "暂时无法连接本地服务，请检查服务后刷新。"
          : "暂时无法确认操作结果。请恢复服务并刷新核对，避免反复提交。",
      );
    }
    if (!response.ok) {
      const code =
        response.status === 401
          ? "UNAUTHENTICATED"
          : (result?.error?.code ?? "UNAVAILABLE");
      const messages: Record<string, string> = {
        UNAUTHENTICATED:
          path === "/auth/login"
            ? "账号或密码不正确，请重新输入。"
            : "登录已过期，请重新登录。",
        VERSION_CONFLICT: "业务或消息已更新，请刷新并重新核对当前提议。",
        APPROVAL_STALE: "来源消息已变化，请刷新并重新核对。",
        SCHEDULE_CONFLICT: "该时段与其他预约冲突，不能确认，请刷新查看。",
        CONSENT_REVOKED: "当前处理授权已暂停，请联系接入负责人核对。",
        CSRF_REJECTED: "登录验证已变化，请退出后重新登录。",
        NOT_FOUND: "当前业务或对话不可用，请刷新并确认使用了回放环境。",
      };
      throw new WorkspaceError(
        code,
        messages[code] ??
          (body === undefined
            ? "暂时无法读取数据，请检查本地服务后刷新。"
            : "操作未能完成或结果暂无法确认，请刷新核对后再操作。"),
      );
    }
    if (result === null)
      throw new WorkspaceError(
        "INVALID_RESPONSE",
        "服务响应无效，请刷新核对当前状态。",
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
      `${path}?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
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
        "列表数据无效，请刷新重试。",
      );
    }
    items.push(...page.items);
    cursor = page.next_cursor;
    if (cursor && seen.has(cursor))
      throw new WorkspaceError(
        "INVALID_RESPONSE",
        "分页数据未能完整读取，请刷新重试。",
      );
    if (cursor) seen.add(cursor);
  } while (cursor);
  return items;
}

export type ReplaySnapshot = {
  orders: Order[];
  tasks: Task[];
  calendar: Calendar[];
  selected: string;
  changes: Change[];
  messages: Message[];
  contextVersion: number;
};
export type ReplayApi = {
  load(selected: string, signal: AbortSignal): Promise<ReplaySnapshot>;
  replay(scenario: "reschedule" | "available"): Promise<boolean>;
  confirm(snapshot: ReplaySnapshot, change: Change): Promise<void>;
};

export function replayApi(request: RequestApi): ReplayApi {
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
          "当前工单没有可核对的对话，请联系后端负责人。",
        );
      const [changes, messages, info] = await Promise.all([
        allPages<Change>(request, `/work-orders/${order.id}/changes`, signal),
        allPages<Message>(
          request,
          `/conversations/${conversation}/messages`,
          signal,
        ),
        request<Detail<{ context_version: number }>>(
          `/conversations/${conversation}`,
          undefined,
          signal,
        ),
      ]);
      return {
        orders,
        tasks,
        calendar,
        selected: order.id,
        changes,
        messages: messages.sort(
          (a, b) =>
            a.occurred_at.localeCompare(b.occurred_at) ||
            a.id.localeCompare(b.id),
        ),
        contextVersion: info.data.context_version,
      };
    },
    async replay(scenario) {
      const result = await request<
        Detail<components["schemas"]["ReplayResult"]>
      >("/replay", { scenario });
      return result.data.duplicate;
    },
    async confirm(snapshot, change) {
      const order = snapshot.orders.find((o) => o.id === snapshot.selected);
      if (!order || order.id !== change.work_order_id)
        throw new WorkspaceError(
          "VERSION_CONFLICT",
          "业务已切换，请刷新并重新核对。",
        );
      await request(`/work-orders/${order.id}/changes/${change.id}/confirm`, {
        expected_version: order.version,
        expected_context_version: snapshot.contextVersion,
        apply_calendar_update: true,
      });
    },
  };
}
