# site · Quartz 站点配置

这里只放**配置**，不放 Quartz 框架代码。CI 与本地预览脚本会：

1. 克隆 `jackyzha0/quartz` 的 `v4.4.0` 到 `.quartz/`（已 gitignore）；
2. 用本目录的 `quartz.config.ts` / `quartz.layout.ts` 覆盖模板配置；
3. 用 `kb.py publish` 生成的 `.publish/` 作为内容目录构建。

## 为什么锁 4.4.0

- Quartz 4.5+ 要求 Node ≥ 22；4.4.0 支持 Node 20。
- 4.4.0 的配置 API 与 `quartz.config.ts` 一致，升级时只需改 `ref` 与 workflow 里的 Node 版本。

## 关键配置

- `baseUrl` 从环境变量 `QUARTZ_BASE_URL` 读（CI 由 `actions/configure-pages` 提供），本地默认 `localhost:8080`。
- `ignorePatterns` 里显式列了内部目录：这是第二道防线，第一道是 `publish` 的白名单。
- `markdownLinkResolution: "absolute"`：库内双链写的是全路径（`[[30_Cards/xxx]]`），必须按绝对路径解析。

## 本地预览

```powershell
powershell -ExecutionPolicy Bypass -File ..\90_Meta\scripts\preview.ps1
```
