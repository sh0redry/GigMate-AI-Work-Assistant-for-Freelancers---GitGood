import { useCallback, useState, type SetStateAction } from "react";
import { stableShare } from "./read-cache.ts";
export function useStableState<T>(initial: T | (() => T)) {
  const [value, setValue] = useState(initial);
  const set = useCallback(
    (next: SetStateAction<T>) =>
      setValue((previous) =>
        stableShare(
          previous,
          typeof next === "function" ? (next as (p: T) => T)(previous) : next,
        ),
      ),
    [],
  );
  return [value, set] as const;
}
