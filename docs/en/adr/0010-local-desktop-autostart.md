# ADR 0010: local desktop automatic startup and explicit clean installation

Status: implemented desktop candidate, native distribution acceptance recorded in release notes. Date: 2026-10-18.

The team has no hosted backend. Reuse the existing UI in Electron with a separately sandboxed business renderer, a same-origin loopback static/API proxy and a Node main process managing local Docker through argument arrays. Do not replace PostgreSQL with the test SQLite fallback. A separate worker and transactional send revalidation remain authoritative.

The installer ships an allowlisted source snapshot plus compiled web assets, not developer configuration, databases, sessions or a Docker engine. Initial setup invokes official Docker installation guidance when needed and requires the user's OS/license interaction. Subsequent launches start the existing Docker stack automatically. The model key uses the OS secret store and a private backend-only volume; business content has no Node/preload privileges. IPC setup methods accept only the separate local setup window. Local-only Docker sockets, loopback-only exposed API ports, trusted origins, CSRF and independent account login remain enforced.

Kyrie explicitly requested removing legacy GigMate runtime data on installation. The first setup therefore requires a visible clean-install acknowledgement before deleting only inspected, known GigMate containers/volumes and the app's private runtime/browser partitions. A unique profile supplies fresh database credentials, connector identity, empty authorization and browser storage. Normal restarts never reset data. Source repositories and other Docker projects are neither searched nor removed. Reinstall generation is marked on Windows and checked against the installed build/executable on startup.

Manual field correction is a sourced merchant command, not an AI permission. It validates ownership, current order/context/source revisions and explicit customer-confirmation attribution, then reuses existing confirmation/calendar/task rules atomically. Non-dispatched drafts are invalidated; dispatched/unknown outcomes remain for reconciliation. No new relational tables are needed; additive wire contracts and generated schemas/types document the command.

Consequences: initial Internet downloads and Docker resources are required; GitHub builds supply macOS arm64/x64 and Windows x64 artifacts. Signing/notarization, automatic updates, Windows ARM, background operation after quit and full real-phone acceptance are not implied. See the [installation guide](../desktop-installation.md).
