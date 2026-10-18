import { useEffect } from "react";

// One scheduler owns cancellation, overlap prevention and bounded network backoff.
// Callers keep business/privacy decisions and validate before publishing results.
export function usePolling(
  task: (signal: AbortSignal) => Promise<void>,
  delay: number,
  enabled: boolean,
  onError: (error: unknown) => void,
  stopped: () => boolean,
) {
  useEffect(() => {
    if (!enabled) return;
    const abort = new AbortController();
    let running = false;
    let failures = 0;
    let retryAt = 0;
    async function run() {
      if (
        running ||
        abort.signal.aborted ||
        stopped() ||
        document.hidden ||
        Date.now() < retryAt
      )
        return;
      running = true;
      try {
        await task(abort.signal);
        if (!abort.signal.aborted && !stopped()) {
          failures = 0;
          retryAt = 0;
        }
      } catch (error) {
        if (!abort.signal.aborted && !stopped()) {
          failures++;
          retryAt =
            Date.now() + Math.min(60000, delay * 2 ** Math.min(failures, 5));
          onError(error);
          if (stopped()) {
            abort.abort();
            clearInterval(timer);
          }
        }
      } finally {
        running = false;
      }
    }
    const timer = setInterval(run, delay);
    void run();
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [task, delay, enabled, onError, stopped]);
}
