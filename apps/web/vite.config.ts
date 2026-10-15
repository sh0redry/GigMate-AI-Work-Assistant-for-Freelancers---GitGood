import { defineConfig, type ProxyOptions } from "vite";
export function developmentTarget(env: Record<string, string | undefined>) {
  const target = env.GIGMATE_REAL_API_URL ?? "http://127.0.0.1:18702";
  if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(target))
    throw new Error(
      "GigMate development target must be a local HTTP backend URL",
    );
  const port = Number(new URL(target).port);
  if (port < 1 || port > 65535)
    throw new Error("GigMate backend port must be between 1 and 65535");
  return target;
}
export function applicationProxy(target: string): ProxyOptions {
  return {
    target,
    configure(proxy) {
      proxy.on("proxyReq", (request, incoming) => {
        const cookie = incoming.headers.cookie
          ?.split(";")
          .map((v) => v.trim())
          .find((v) => v.startsWith("gigmate_session="));
        if (cookie) request.setHeader("cookie", cookie);
        else request.removeHeader("cookie");
      });
      proxy.on("proxyRes", (response) => {
        if (response.headers["set-cookie"])
          response.headers["set-cookie"] = response.headers[
            "set-cookie"
          ].filter((v) => v.startsWith("gigmate_session="));
      });
    },
  };
}
export default defineConfig(({ command }) => ({
  server: {
    host: "127.0.0.1",
    proxy:
      command === "serve"
        ? { "/api": applicationProxy(developmentTarget(process.env)) }
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
}));
