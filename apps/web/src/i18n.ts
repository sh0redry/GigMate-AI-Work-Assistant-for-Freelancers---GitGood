import { useSyncExternalStore } from "react";
import { english, cantonese } from "./locales.ts";
export type Locale = "zh" | "en" | "yue";
const listeners = new Set<() => void>();
let locale: Locale = "zh";
try {
  const saved = globalThis.localStorage?.getItem("gigmate-ui-language");
  if (saved === "zh" || saved === "en" || saved === "yue") locale = saved;
} catch {
  /* A language preference must never block login. */
}
export function setLocale(next: Locale) {
  if (!["zh", "en", "yue"].includes(next) || next === locale) return;
  locale = next;
  try {
    globalThis.localStorage?.setItem("gigmate-ui-language", next);
  } catch {
    /* memory-only */
  }
  if (globalThis.document)
    document.documentElement.lang =
      next === "en" ? "en-HK" : next === "yue" ? "yue-Hant-HK" : "zh-CN";
  listeners.forEach((fn) => fn());
}
export function getLocale() {
  return locale;
}
export function useLocale() {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    getLocale,
    () => "zh" as Locale,
  );
}
const reverse = new Map<string, string>();
for (const [key, value] of Object.entries(english)) reverse.set(value, key);
for (const [key, value] of Object.entries(cantonese)) reverse.set(value, key);
const templates: { key: string; pattern: RegExp; positions: number[] }[] = [];
function prepareTemplates() {
  if (templates.length) return;
  for (const key of Object.keys(english).filter((k) => /\{\d+\}/.test(k))) {
    for (const value of new Set([key, english[key], cantonese[key]])) {
      if (!value) continue;
      const positions: number[] = [];
      let expression = "",
        offset = 0;
      for (const match of value.matchAll(/\{(\d+)\}/g)) {
        expression +=
          value
            .slice(offset, match.index)
            .replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "([\\s\\S]*?)";
        positions.push(Number(match[1]));
        offset = match.index! + match[0].length;
      }
      expression += value.slice(offset).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      templates.push({
        key,
        pattern: new RegExp("^" + expression + "$"),
        positions,
      });
    }
  }
}
export function t(source: string, ...values: unknown[]): string {
  let key = Object.hasOwn(english, source)
    ? source
    : (reverse.get(source) ?? source);
  // Only UI-created notices/reviews enter t(); customer text never does.
  // This lets an already formatted notice follow a later language change.
  if (
    !values.length &&
    key === source &&
    !Object.hasOwn(english, key) &&
    source.length < 8192
  ) {
    prepareTemplates();
    for (const item of templates) {
      const matched = source.match(item.pattern);
      if (!matched) continue;
      key = item.key;
      item.positions.forEach((position, i) => {
        values[position] = matched[i + 1];
      });
      break;
    }
  }
  const text =
    (locale === "en"
      ? english[key]
      : locale === "yue"
        ? cantonese[key]
        : key) ?? source;
  return text.replace(/\{(\d+)\}/g, (match, i: string) =>
    Number(i) < values.length ? String(values[Number(i)]) : match,
  );
}
// Only static UI dictionaries pass through this helper. Business/customer data never does.
const proxies = new WeakMap<object, object>();
export function localized<T extends object>(value: T): T {
  if (proxies.has(value)) return proxies.get(value) as T;
  const proxy = new Proxy(value, {
    get(target, key, receiver) {
      const item = Reflect.get(target, key, receiver);
      if (typeof item === "string") return t(item);
      if (item && typeof item === "object") return localized(item);
      return item;
    },
  });
  proxies.set(value, proxy);
  return proxy;
}
