import { defineConfig, type ProxyOptions } from "vite";

type Environment = "real" | "isolated";
export function developmentEnvironments(
  env: Record<string, string | undefined>,
) {
  const targets = {
    real: env.GIGMATE_REAL_API_URL ?? "http://127.0.0.1:18702",
    isolated:
      env.GIGMATE_ISOLATED_API_URL ??
      env.GIGMATE_API_URL ??
      "http://127.0.0.1:18000",
  };
  for (const target of Object.values(targets)) {
    if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(target))
      throw new Error(
        "GigMate development targets must be local HTTP backend URLs",
      );
    const port = Number(new URL(target).port);
    if (port < 1 || port > 65535)
      throw new Error("GigMate backend port must be between 1 and 65535");
  }
  if (new URL(targets.real).port === new URL(targets.isolated).port)
    throw new Error(
      "Real and isolated environments must use separate backend ports and databases",
    );
  const defaultEnvironment = env.GIGMATE_DEFAULT_ENV ?? "isolated";
  if (defaultEnvironment !== "real" && defaultEnvironment !== "isolated")
    throw new Error("GIGMATE_DEFAULT_ENV must be real or isolated");
  return {
    targets,
    defaultEnvironment,
    publicTestAccount: {
      username: "merchant",
      password: "demo-only-change-me",
    },
  };
}
export function environmentProxy(
  environment: Environment,
  target: string,
): ProxyOptions {
  const prefix = `/environments/${environment}`;
  const cookieName = `gigmate_session_${environment}`;
  return {
    target,
    rewrite: (path) => path.slice(prefix.length),
    cookiePathRewrite: prefix + "/",
    configure(proxy) {
      proxy.on("proxyReq", (request, incoming) => {
        // Forward only this environment's session, including when paths overlap.
        const cookie = incoming.headers.cookie
          ?.split(";")
          .map((part) => part.trim())
          .find((part) => part.startsWith(cookieName + "="));
        if (cookie)
          request.setHeader(
            "cookie",
            "gigmate_session=" + cookie.slice(cookieName.length + 1),
          );
        else request.removeHeader("cookie");
      });
      proxy.on("proxyRes", (response) => {
        const cookies = response.headers["set-cookie"];
        if (cookies)
          response.headers["set-cookie"] = cookies
            .filter((cookie) => cookie.startsWith("gigmate_session="))
            .map((cookie) =>
              cookie.replace(/^gigmate_session=/, cookieName + "="),
            );
      });
    },
  };
}
export default defineConfig(({ command }) => {
  const config =
    command === "serve" ? developmentEnvironments(process.env) : null;
  return {
    // Only public loopback destinations, never provider keys/private setup.
    // Published builds use /api and expose no development credential hints.
    define: { __GIGMATE_ENVIRONMENTS__: JSON.stringify(config) },
    server: {
      host: "127.0.0.1",
      proxy: config
        ? {
            "/environments/real/api": environmentProxy(
              "real",
              config.targets.real,
            ),
            "/environments/isolated/api": environmentProxy(
              "isolated",
              config.targets.isolated,
            ),
          }
        : undefined,
      fs: {
        deny: [
          ".env",
          ".env.*",
          "*.{crt,pem,key,p12,pfx,cer,der}",
          ".npmrc",
          ".yarnrc.yml",
          "**/.git/**",
          "**/local-data/**",
        ],
      },
    },
  };
});
