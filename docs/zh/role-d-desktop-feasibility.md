# GigMate 桌面与可安装应用可行性

2026-10-16 当前候选：已提供网页安装信息／图标和独立窗口启动资料，没有安装离线业务缓存。浏览器安装取决于 [MDN 条件](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)，原生安装／实体设备验收仍待完成；没有生成 exe／macOS 安装器或签名。见[当前验收](role-d-final-acceptance.md)，下方评估为旧日期历史。

2026-10-12 · 仅作评估；没有生成 exe、macOS app、安装器、签名或部署。[English counterpart](../en/role-d-desktop-feasibility.md)。

现有 React/TypeScript/Vite 界面可复用于 Windows 和 macOS。但前端打包不会自动包含 FastAPI、独立 worker、PostgreSQL 和 WAHA，也不会解决生产认证、持久任务、审批重验和未知结果核对。浏览器目前采用同源 session cookie、CSRF 和相对 `/api/v1` 路径；桌面外壳必须保留可信应用来源／后端代理，不能关闭校验或把连接器密钥放进 JavaScript。

| 方案 | 适用与代价 |
| --- | --- |
| 可安装 PWA | 对已部署 HTTPS 服务改动最少，可支持手机主屏和浏览器安装；并非独立 Windows exe。需 manifest／安装策略和明确缓存规则，业务正文、会话数据和二维码不进入离线缓存；离线写入保持禁用 |
| Tauri 2 | 系统 webview 复用编译的网页资产，并用 Rust／原生能力；适合评估较小的 Windows/macOS 外壳，但新增 Rust 和各平台 webview／工具链验收 |
| Electron | 捆绑 Chromium/Node，复用网页支持 Windows/macOS/Linux；JavaScript 工具熟悉、浏览器引擎一致，但随包运行时较多，必须严格限制渲染进程权限 |

对当前仓库的建议：先把 D-02 至 D-04 的 Web 主线做稳，再评估带安全托管后端的 PWA。若明确需要 exe/app，再用现有界面和同一鉴权后端做 Tauri 原型；团队更重视 JavaScript 工具与 Chromium 一致性时，可选择 Electron。这是工程判断，不是实测性能结论，也不是已采纳的架构变更。

先决定部署边界：（1）桌面客户端连接托管 API/worker/数据库／私有连接器，打包较简单，但生产服务和身份仍未完成；（2）完全本机安装需要管理 Python/worker/PostgreSQL/WAHA 及容器依赖的生命周期、升级、备份、迁移、端口和密钥。如果仍依赖 Docker，安装器必须说明。不能因为测试支持 SQLite，就默默替换 PostgreSQL；这需要独立架构决策。

未来获授权的打包批次应记录 ADR、保留权限边界、定义签名更新／迁移回滚／私有数据路径，并测试全新安装／卸载不删业务数据、重启任务恢复、登录／CSRF、来源失效、断线／未知结果以及原生 Windows/macOS。签名、公证和应用商店是各平台独立门槛。本次评估不添加打包依赖或空原生目录。

2026-10-12 核对来源：[Tauri 介绍](https://v2.tauri.app/start/)、[Electron 前提](https://www.electronjs.org/docs/latest/tutorial/tutorial-prerequisites)、[MDN PWA 介绍](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)。官方资料证明各框架的打包／运行方式，不证明 GigMate 已兼容或具体包大小。
