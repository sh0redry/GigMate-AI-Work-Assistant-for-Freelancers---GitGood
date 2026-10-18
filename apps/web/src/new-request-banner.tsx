import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { useEffect, useMemo } from "react";
import { allPages, workspaceApi } from "./workspace-api";
import type { components } from "./generated/api";

type Suggestion = components["schemas"]["NewOrderSuggestionView"];

/**
 * "The customer mentioned something new": AI new-order suggestions waiting on
 * the merchant, including a second job noticed next to a change to an
 * existing order. One click opens new-order creation with it prefilled.
 */
export function NewRequestBanner({
  csrf,
  refreshKey,
  onOpen,
}: {
  csrf: string;
  refreshKey?: unknown;
  onOpen: (suggestionId: string) => void;
}) {
  const api = useMemo(() => workspaceApi(csrf), [csrf]);
  const [items, setItems] = useState<Suggestion[]>([]);
  useEffect(() => {
    const abort = new AbortController();
    allPages<Suggestion>(api, "/new-order-suggestions", abort.signal)
      .then((list) => {
        if (!abort.signal.aborted) setItems(list);
      })
      .catch(() => {
        // A hint only: the page works without it.
        if (!abort.signal.aborted) setItems([]);
      });
    return () => abort.abort();
  }, [api, refreshKey]);
  if (!items.length) return null;
  const first = items[0];
  return (
    <div className="notice new-request" role="status">
      <p>
        {items.length === 1
          ? t("客人提到一件新事：「{0}」。", first.suggestion.summary)
          : t(
              "客人提到 {0} 件新事，最新一件：「{1}」。",
              items.length,
              first.suggestion.summary,
            )}
      </p>
      <button type="button" onClick={() => onOpen(first.id)}>
        {t("另开一单（已预填）")}
      </button>
    </div>
  );
}
