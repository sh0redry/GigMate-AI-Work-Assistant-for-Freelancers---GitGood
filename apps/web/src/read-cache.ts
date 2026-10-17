// Private, session-memory snapshots. Every read still reaches the authenticated
// server; a cached value is usable only after its matching 304 response.
type Entry = { body: string; etag: string };
let scope = "",
  epoch = 0;
let stores = new WeakMap<typeof fetch, Map<string, Entry>>();
export function clearReadCache() {
  epoch++;
  stores = new WeakMap();
}
export function setReadScope(value: string) {
  if (value !== scope) {
    scope = value;
    clearReadCache();
  }
}
export function privateReadPath(url: string) {
  return (
    url.startsWith("/api/v1/") &&
    !/\/(?:auth|replay)(?:\/|$)|\/qr(?:\?|$)|\/content(?:\?|$)|\.ics(?:\?|$)/.test(
      url,
    )
  );
}
export async function sessionFetch(
  url: string,
  init: RequestInit = {},
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase(),
    reading = method === "GET";
  if (!reading) clearReadCache();
  const start = epoch,
    owner = scope;
  const eligible = reading && !!owner && privateReadPath(url);
  let cache = stores.get(fetcher);
  if (!cache) {
    cache = new Map();
    stores.set(fetcher, cache);
  }
  const key = url + "\n" + new Headers(init.headers).get("X-CSRF-Token");
  const previous = eligible ? cache.get(key) : undefined;
  const headers = new Headers(init.headers);
  if (previous) headers.set("If-None-Match", previous.etag);
  // Preserve plain headers for existing adapters; never cache a failed response.
  const options = {
    ...init,
    headers: previous ? Object.fromEntries(headers.entries()) : init.headers,
  };
  let response: Response;
  try {
    response = await fetcher(url, options);
  } finally {
    if (!reading) clearReadCache();
  }
  if (init.signal?.aborted) throw new DOMException("Cancelled", "AbortError");
  if (start !== epoch || owner !== scope) {
    if (reading && owner)
      throw new DOMException("Session changed", "AbortError");
    return response;
  }
  if ([401, 403, 404].includes(response.status)) clearReadCache();
  if (response.status === 304) {
    if (
      !eligible ||
      !previous ||
      response.headers.get("etag") !== previous.etag
    )
      throw Error("Unmatched conditional response");
    return new Response(previous.body, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        ETag: previous.etag,
        "Cache-Control": "private, no-store",
      },
    });
  }
  const etag = response.headers.get("etag");
  if (
    eligible &&
    response.ok &&
    etag &&
    /application\/json/i.test(response.headers.get("content-type") ?? "")
  ) {
    const body = await response.clone().text();
    if (start === epoch && owner === scope && body.length <= 1024 * 1024) {
      if (cache.size >= 120) cache.delete(cache.keys().next().value!);
      cache.set(key, { body, etag });
    }
  }
  return response;
}
// Preserve references for equal JSON subtrees, including arrays. Opaque values
// (File, Blob, Date, Map) are deliberately never compared or persisted.
export function stableShare<T>(previous: T, next: T): T {
  if (Object.is(previous, next)) return previous;
  if (
    !previous ||
    !next ||
    typeof previous !== "object" ||
    typeof next !== "object"
  )
    return next;
  if (Array.isArray(previous) && Array.isArray(next)) {
    const values = next.map((v, i) => stableShare(previous[i], v));
    return (
      previous.length === next.length &&
      values.every((v, i) => v === previous[i])
        ? previous
        : values
    ) as T;
  }
  if (
    Object.getPrototypeOf(previous) !== Object.prototype ||
    Object.getPrototypeOf(next) !== Object.prototype
  )
    return next;
  const old = previous as Record<string, unknown>,
    value = next as Record<string, unknown>;
  const keys = Object.keys(value),
    shared = Object.fromEntries(
      keys.map((k) => [k, stableShare(old[k], value[k])]),
    );
  return (
    Object.keys(old).length === keys.length &&
    keys.every((k) => Object.hasOwn(old, k) && old[k] === shared[k])
      ? previous
      : shared
  ) as T;
}
export function privateReadDenied(e: unknown) {
  const code = (e as { code?: string })?.code;
  return !!code && !["NETWORK_ERROR", "UNAVAILABLE"].includes(code);
}
