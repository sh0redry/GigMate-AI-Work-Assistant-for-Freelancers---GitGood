export const accountId = "00000000-0000-4000-8000-000000000001";
export function action(overrides = {}) {
  return {
    id: "a1",
    account_id: accountId,
    work_order_id: "order",
    conversation_id: "chat",
    recipient: "chat",
    kind: "send_text",
    revision: 1,
    state: "pending_approval",
    body: "收到，你想改到 10/17 15:00。这个时间已有安排，可以换个时间吗？",
    trigger: "schedule_conflict",
    bound_work_order_version: 3,
    bound_context_version: 4,
    snapshot_hash: "sha256:" + "a".repeat(64),
    expires_at: "2099-10-17T00:00:00Z",
    approved_by: null,
    approved_at: null,
    idempotency_key: "synthetic",
    provider_message_id: null,
    delivery_status: "not_submitted",
    sources: [{ message_id: "m1", message_revision: 1 }],
    closed_reason: null,
    closed_note: null,
    reissuable: false,
    ...overrides,
  };
}
export function fixture() {
  const data = {
    actions: [action()],
    order: {
      id: "order",
      account_id: accountId,
      summary: "Synthetic portrait booking",
      version: 3,
      status: "confirmed",
      conversation_ids: ["chat"],
    },
    conversation: {
      id: "chat",
      account_id: accountId,
      context_version: 4,
      work_order_ids: ["order"],
      provider_conversation_id: "synthetic-owned-chat",
    },
    messages: [
      {
        id: "m1",
        account_id: accountId,
        conversation_id: "chat",
        revision: 1,
        text: "想改到星期六三点。",
        occurred_at: "2026-10-13T01:00:00Z",
        revoked: false,
      },
    ],
    denied: false,
    offline: false,
    drop: false,
    delayed: null,
    writes: [],
    reads: [],
    cached: new Map(),
  };
  const fetcher = async (url, options = {}) => {
    const parsed = new URL(url, "http://localhost");
    const path = parsed.pathname.replace(/^.*\/api\/v1/, "");
    if (options.method === "POST") {
      const body = JSON.parse(options.body);
      const operation = path.split("/").at(-1);
      data.writes.push({ url, options: { ...options }, body, operation });
      if (data.delayed) await data.delayed;
      const key = options.headers["Idempotency-Key"];
      if (data.cached.has(key))
        return Response.json({ data: data.cached.get(key) });
      const index = data.actions.findIndex((a) =>
        path.includes(`/actions/${a.id}/`),
      );
      const current = data.actions[index];
      if (!current)
        return Response.json({ error: { code: "NOT_FOUND" } }, { status: 404 });
      if (
        (operation === "approve" &&
          (body.expected_context_version !==
            data.conversation.context_version ||
            body.snapshot_hash !== current.snapshot_hash ||
            current.state !== "pending_approval")) ||
        (data.denied && ["approve", "reissue"].includes(operation))
      )
        return Response.json(
          { error: { code: "APPROVAL_STALE" } },
          { status: 409 },
        );
      let result;
      if (operation === "reissue") {
        result = action({
          id: "new-action",
          bound_context_version: data.conversation.context_version,
        });
        data.actions.push(result);
      } else {
        result = {
          ...current,
          state: operation === "approve" ? "approved" : "cancelled",
          approved_at: operation === "approve" ? "2026-10-13T01:00:00Z" : null,
          approved_by: operation === "approve" ? accountId : null,
          closed_reason:
            operation === "reject"
              ? "rejected"
              : operation === "cancel"
                ? "cancelled"
                : null,
          closed_note: body.reason ?? null,
        };
        data.actions[index] = result;
      }
      data.cached.set(key, structuredClone(result));
      if (data.drop) {
        data.drop = false;
        throw new TypeError("synthetic lost reply");
      }
      return Response.json({ data: result });
    }
    data.reads.push(url);
    if (data.offline) throw new TypeError("synthetic outage");
    if (path === "/actions")
      return Response.json({ items: data.actions, next_cursor: null });
    if (path.startsWith("/actions/"))
      return Response.json({
        data: data.actions.find((a) => a.id === path.split("/").at(-1)),
      });
    if (path === "/work-orders")
      return Response.json({ items: [data.order], next_cursor: null });
    if (path === "/work-orders/order")
      return Response.json({ data: data.order });
    if (path.startsWith("/conversations/")) {
      if (data.denied)
        return Response.json({ error: { code: "NOT_FOUND" } }, { status: 404 });
      return path.endsWith("/messages")
        ? Response.json({ items: data.messages, next_cursor: null })
        : Response.json({ data: data.conversation });
    }
    throw new Error("Unexpected route " + path);
  };
  return { data, fetcher };
}
export function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    values,
  };
}
