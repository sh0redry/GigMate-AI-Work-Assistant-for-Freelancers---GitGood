import type { Choice } from "./connection-api";

export type ChatFilter = "all" | "direct" | "group" | "unknown" | "selected";

export function choiceKind(choice: Choice) {
  return choice.kind === "direct" || choice.kind === "group"
    ? choice.kind
    : "unknown";
}

export function choiceDisplay(choice: Choice) {
  const kind = choiceKind(choice);
  const kindLabel = {
    direct: "个人聊天",
    group: "群聊",
    unknown: "类型未提供",
  }[kind];
  const label = choice.label.trim();
  const placeholder =
    !label || ["Authorized conversation", "已授权会话"].includes(label);
  return {
    kind,
    kindLabel,
    label: placeholder
      ? choice.selected
        ? `已授权${kind === "group" ? "群聊" : kind === "direct" ? "个人聊天" : "会话"}`
        : `未命名${kind === "group" ? "群聊" : kind === "direct" ? "个人聊天" : "会话"}`
      : label,
    numberOnly:
      !placeholder && kind === "direct" && /^\+?\d[\d\s().-]{5,}$/.test(label),
  };
}

// Pagination is a view over the complete loaded catalog, never a consent subset.
export function choicePage(
  choices: Choice[],
  search: string,
  filter: ChatFilter,
  requestedPage: number,
  pageSize: number,
) {
  const size = [8, 16, 24].includes(pageSize) ? pageSize : 8;
  const query = search.trim().toLocaleLowerCase();
  const filtered = choices
    .map((choice, index) => ({ choice, index, ...choiceDisplay(choice) }))
    .filter(
      (item) =>
        item.label.toLocaleLowerCase().includes(query) &&
        (filter === "all" ||
          (filter === "selected"
            ? item.choice.selected
            : item.kind === filter)),
    );
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  const page = Math.min(
    pages,
    Math.max(1, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 1),
  );
  return {
    items: filtered.slice((page - 1) * size, page * size),
    page,
    pages,
    total: filtered.length,
    start: filtered.length ? (page - 1) * size + 1 : 0,
    end: Math.min(page * size, filtered.length),
  };
}
