import { t } from "./i18n.ts";
import { useStableState as useState } from "./useStableState";
import { privateReadDenied } from "./read-cache.ts";
import { useCallback, useEffect, useRef } from "react";
import { workspaceApi, type RequestApi } from "./workspace-api.ts";
export function useWorkspaceData<T>(
  csrf: string,
  expired: () => void,
  load: (api: RequestApi, signal: AbortSignal) => Promise<T>,
) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const hasData = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    setLoading(!hasData.current);
    setError("");
    try {
      const value = await load(workspaceApi(csrf), next.signal);
      if (!next.signal.aborted) {
        setData(value);
        hasData.current = true;
        setError("");
      }
    } catch (e) {
      if (!next.signal.aborted) {
        if (privateReadDenied(e)) {
          setData(null);
          hasData.current = false;
        }
        setError(e instanceof Error ? e.message : t("暂时无法读取，请刷新。"));
        if ((e as { code?: string })?.code === "UNAUTHENTICATED") expired();
      }
    } finally {
      if (!next.signal.aborted) setLoading(false);
    }
  }, [csrf, expired, load]);
  useEffect(() => {
    void refresh();
    return () => controller.current?.abort();
  }, [refresh]);
  return { data, error, loading, refresh };
}
