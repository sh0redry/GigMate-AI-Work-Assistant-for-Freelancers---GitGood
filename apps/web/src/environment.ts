export type EnvironmentId = "real" | "isolated";
export type EnvironmentConfig = {
  defaultEnvironment: EnvironmentId;
  publicTestAccount: { username: string; password: string };
  targets: Record<EnvironmentId, string>;
};
declare const __GIGMATE_ENVIRONMENTS__: EnvironmentConfig | null;

export function environmentConfig(): EnvironmentConfig | null {
  return typeof __GIGMATE_ENVIRONMENTS__ === "undefined"
    ? null
    : __GIGMATE_ENVIRONMENTS__;
}
export function currentEnvironment(): EnvironmentId | null {
  const config = environmentConfig();
  if (!config) return null;
  const path = typeof window === "undefined" ? "" : window.location.pathname;
  if (path.startsWith("/environments/real/")) return "real";
  if (path.startsWith("/environments/isolated/")) return "isolated";
  return config.defaultEnvironment;
}
export function apiBase(): string {
  const environment = currentEnvironment();
  return environment ? `/environments/${environment}/api/v1` : "/api/v1";
}
export function attemptNamespace(): string {
  const environment = currentEnvironment();
  return environment
    ? `gigmate-control-attempt:${environment}:`
    : "gigmate-control-attempt:";
}
