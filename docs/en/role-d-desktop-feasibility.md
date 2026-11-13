# GigMate desktop and installable-app feasibility

Current 2026-10-16 candidate: a web manifest/icon and standalone start metadata are implemented, with no service worker/offline business cache. Browser installation is subject to [MDN requirements](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable); native install/device acceptance is pending. No exe/macOS installer/signing is delivered. See [current acceptance](role-d-final-acceptance.md). The assessment below is dated history.

2026-10-12 · Assessment only; no exe, macOS app, installer, distribution signing or deployment was built. [Chinese counterpart](../zh/role-d-desktop-feasibility.md).

The React/TypeScript/Vite UI can be reused for Windows and macOS. Packaging the UI alone does not package FastAPI, its separate worker, PostgreSQL or WAHA, nor solve production authentication, persistent jobs, approval revalidation or unknown-outcome reconciliation. The current browser uses same-origin session cookies, CSRF and `/api/v1` relative paths; a shell must preserve a trusted application origin/backend proxy, not disable those checks or put connector secrets in JavaScript.

| Option | Fit and tradeoff |
| --- | --- |
| Installable PWA | Lowest frontend disruption for a hosted HTTPS service, mobile home-screen use and browser installation. It is not a standalone Windows exe. Requires a manifest/install strategy and a deliberate caching policy; business content, session data and QR should not become offline caches. Offline mutations must stay blocked |
| Tauri 2 | Reuse compiled web assets in the system webview with Rust/native support. Candidate for a smaller Windows/macOS shell; introduces Rust and platform webview/toolchain acceptance |
| Electron | Reuse web UI with bundled Chromium/Node for Windows/macOS/Linux. Familiar JavaScript tooling and consistent browser engine; bundles more runtime and requires strict renderer/process permissions |

Recommendation for this repository: keep D-02 through D-04 on Web first. Then evaluate PWA with a securely hosted backend; if an explicit exe/app is needed, prototype Tauri around the existing UI with the same authenticated backend. Electron is a reasonable alternative if the team prioritizes JavaScript tooling and Chromium consistency. This preference is an engineering inference, not a measured benchmark or an adopted architectural change.

Decide deployment first: (1) a desktop client with a hosted API/worker/database/private connector is the simpler packaging boundary, but those production services and identity remain unimplemented; (2) a fully local installation must manage the lifecycle, upgrades, backups, migrations, ports and secrets of Python/worker/PostgreSQL/WAHA and their container dependencies. An installer that still requires Docker should disclose that; replacing PostgreSQL with SQLite is a separate architectural change and cannot be inferred from test fallback support.

A future authorized packaging batch should record an ADR, preserve permission boundaries, define signed update/migration rollback and private data paths, then test fresh install/uninstall without deleting business data, restart/job recovery, login/CSRF, source invalidation, disconnected/unknown outcomes and native Windows/macOS operation. Signing/notarization and applicable store distribution are platform-specific gates. No packaging dependencies or unused native directories are added by this assessment.

Sources checked on 2026-10-12: [Tauri overview](https://v2.tauri.app/start/), [Electron prerequisites](https://www.electronjs.org/docs/latest/tutorial/tutorial-prerequisites), [MDN PWA overview](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps). Official framework descriptions establish their packaging/runtime approach, not GigMate compatibility or bundle size.


## 2026-10-18 desktop follow-up

Desktop automatic-start and manual correction are now implemented candidates. See [installation, data retention and optional maintenance](desktop-installation.md) for Docker setup, non-destructive installation/reinstall, explicit old-resource cleanup, secrets and unsigned-distribution limits.
