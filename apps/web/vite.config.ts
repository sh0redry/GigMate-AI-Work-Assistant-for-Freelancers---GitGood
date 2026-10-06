import { defineConfig } from "vite";

// Explicitly select Replay (18000) or the developer-owned WAHA ingress (18702).
const target = process.env.GIGMATE_API_URL ?? "http://127.0.0.1:18000";
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(target)) {
  throw new Error("GIGMATE_API_URL must be a local HTTP backend URL");
}
export default defineConfig({
  server: { proxy: { "/api": target, "/health": target } },
});
