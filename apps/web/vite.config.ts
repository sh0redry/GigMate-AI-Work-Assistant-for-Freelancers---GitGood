import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { localPairingMiddleware } from "./local-pairing.mjs";

// Explicitly select Replay (18000) or the developer-owned WAHA ingress (18702).
const target = process.env.GIGMATE_API_URL ?? "http://127.0.0.1:18000";
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(target)) {
  throw new Error("GIGMATE_API_URL must be a local HTTP backend URL");
}
export default defineConfig(({ command }) => {
  const localPairing =
    command === "serve" && process.env.GIGMATE_LOCAL_PAIRING === "1";
  return {
    define: {
      "import.meta.env.GIGMATE_LOCAL_PAIRING": JSON.stringify(localPairing),
    },
    plugins: localPairing
      ? [
          {
            name: "gigmate-local-pairing",
            apply: "serve",
            configureServer(server) {
              server.middlewares.use(
                localPairingMiddleware({
                  target,
                  root: fileURLToPath(new URL("../..", import.meta.url)),
                }),
              );
            },
          },
        ]
      : [],
    server: {
      host: "127.0.0.1",
      proxy: { "/api": target, "/health": target },
      fs: {
        // Preserve Vite's pinned default deny list and protect all private setup.
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
