// The product has one same-origin API. Test fixtures and proxy targets live in
// developer tools, never in browser routing, credentials or environment controls.
export function apiBase(): string {
  return "/api/v1";
}
export function attemptNamespace(): string {
  return "gigmate-control-attempt:";
}
