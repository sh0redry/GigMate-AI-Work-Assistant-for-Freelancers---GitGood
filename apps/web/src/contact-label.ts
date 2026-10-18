import { t } from "./i18n.ts";
import type { components } from "./generated/api";
import { allPages, type RequestApi } from "./workspace-api";

type Conversation = components["schemas"]["Conversation"];

/**
 * A WhatsApp chat id as the merchant knows it: the contact's phone number.
 *
 * `85291234567@c.us` → `+852 9123 4567`. Group chats and chats WhatsApp only
 * exposes as a linked id (`…@lid`) carry no phone number at all, so they get
 * a plain label instead of a made-up number.
 */
export function contactLabel(providerConversationId: string | undefined) {
  if (!providerConversationId) return t("未知联系人");
  const [user, server] = providerConversationId.split("@");
  if (server === "g.us") return t("WhatsApp 群组");
  if (server !== "c.us" || !/^\d{6,15}$/.test(user ?? ""))
    return t("号码未公开的联系人");
  if (user.startsWith("852") && user.length === 11)
    return `+852 ${user.slice(3, 7)} ${user.slice(7)}`;
  if (user.startsWith("86") && user.length === 13)
    return `+86 ${user.slice(2, 5)} ${user.slice(5, 9)} ${user.slice(9)}`;
  return `+${user}`;
}

/**
 * Conversation id → contact label, for every authorised conversation.
 *
 * Display only: if the list cannot be read the page still loads and shows
 * the neutral label, rather than failing the whole review or send flow.
 */
export async function loadContactLabels(
  api: RequestApi,
  signal?: AbortSignal,
): Promise<Map<string, string>> {
  try {
    const list = await allPages<Conversation>(api, "/conversations", signal);
    return new Map(
      list.map((c) => [c.id, contactLabel(c.provider_conversation_id)]),
    );
  } catch {
    return new Map();
  }
}

/** Stable chronological order: oldest first, ties broken by id. */
export function byTime<T extends { id: string }>(time: (item: T) => string) {
  return (a: T, b: T) =>
    Date.parse(time(a)) - Date.parse(time(b)) || a.id.localeCompare(b.id);
}

/** `2026-10-18T06:00:00Z` → `10/18 14:00` in Hong Kong time. */
export function shortTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Hong_Kong",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(parsed);
  const part = (type: string) => parts.find((p) => p.type === type)?.value;
  return `${part("month")}/${part("day")} ${part("hour")}:${part("minute")}`;
}
