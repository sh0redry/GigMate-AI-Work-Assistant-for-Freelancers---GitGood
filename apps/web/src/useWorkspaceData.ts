import { useCallback, useEffect, useRef, useState } from "react";
import { workspaceApi, type RequestApi } from "./workspace-api.ts";
export function useWorkspaceData<T>(
  csrf: string,
  expired: () => void,
  load: (api: RequestApi, signal: AbortSignal) => Promise<T>,
) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    setLoading(true);
    setError("");
    try {
      const value = await load(workspaceApi(csrf), next.signal);
      if (!next.signal.aborted) setData(value);
    } catch (e) {
      if (!next.signal.aborted) {
        setData(null);
        setError(e instanceof Error ? e.message : "暂时无法读取，请刷新。");
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
