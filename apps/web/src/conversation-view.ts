import type { TimelineMessage } from "./waha-sync-api";

export type ConversationIntent = {
  conversationId: string;
  messageId?: string;
  revision?: number;
  token: string;
};

export function orderedMessages(messages: TimelineMessage[]) {
  return [
    ...new Map(messages.map((message) => [message.id, message])).values(),
  ].sort(
    (a, b) =>
      a.occurred_at.localeCompare(b.occurred_at) || a.id.localeCompare(b.id),
  );
}

export function sourceMatch(
  message: TimelineMessage,
  id: string,
  revision: number,
) {
  return (
    message.source_message_id === id &&
    message.evidence === "revision" &&
    message.revision === revision &&
    !message.revoked
  );
}

export function messageSummary(message: TimelineMessage | undefined) {
  // Raw business text: never translate, log or persist this preview in browser storage.
  return message && !message.revoked
    ? (message.text ?? message.filename ?? "")
    : "";
}

export function nearConversationBottom(
  element: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">,
) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}
