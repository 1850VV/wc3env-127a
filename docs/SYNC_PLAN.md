# wc3env-127a 私有仓库同步记录

用户于 2026-10-18 明确批准「按方案 B 创建并推送」。本文件记录已批准范围与过滤结果；远端交付以 GitHub 可见分支和提交为准，不再等待第二次批准。

## 目标与隔离

- 目标：[1850VV/wc3env-127a](https://github.com/1850VV/wc3env-127a)，独立 **private** 仓库。
- 实际发布目录：`C:\Users\vvv\Documents\ChatGPT\wc3env-127a-private`，全新独立 `.git`，无共享 objects。
- 原准备副本 `C:\Users\vvv\Documents\ChatGPT\wc3env-127a-publish` 原样保留，便于追溯审批范围。
- 原源码 `C:\Users\vvv\Documents\ChatGPT\wc3env-127a` 保留原有分支、提交、未提交文件。
- 工作分支：`codex/127a-private-sync`，过滤后基准 `4f2b66179fa766c9228b35990b815386d8edcf08`。
- `origin` 对应用户私有仓库，`upstream` 对应 `https://github.com/pwang724/wc3env.git`。

## 方案 B 实际处理

用现有 Git fast-export/fast-import，将排除 `docs/media/**` 和 `tests/fixtures/*.w3g` 后的四个历史提交导入全新仓库。12 个演示媒体和 2 个过时回放从全部历史中去除。没有安装依赖；没有对原仓库执行 reset、clean、覆盖分支或改写历史。

逐提交确认保留文件的 blob ID/模式、作者、提交者、时间、说明及映射后的父关系一致。两个原 SSH 签名因 SHA 改变而移除。旧、新 SHA 见 [HISTORY_REWRITE.md](HISTORY_REWRITE.md)。

全部发布分支都使用过滤后的历史，不会从开发分支重新上传旧对象。审计既检查可达历史，也检查新对象库物理内容，确认 14 个旧二进制对象不存在，而非只从最新目录隐藏。

## 远端分支与文件

| 分支 | 内容 |
|---|---|
| `main`（默认） | 本次文档、验证工具和证据整理提交 |
| `codex/127a-private-sync` | 与初始 main 相同的整理提交 |
| `codex/wc3-127a` | 过滤后的原移植 `bad0278a39ea1b1ea1233c230677f83f5ecd86a7` |
| `codex/archmage-kiting-mvp` | 过滤后的后续开发 `4f2b66179fa766c9228b35990b815386d8edcf08` |

生产 Python/C Hook 源码没有因发布而改变；SDK、agent、测试、工具目录结构保持原样。整理内容包括 README、忽略规则、移植说明、功能指南、API 兼容表、验证报告、来源/许可证、历史映射、2 个验证脚本及小型证据。完整当前树清单见 [PUBLICATION_FILES.txt](PUBLICATION_FILES.txt)。

游戏安装、地图、美术资源、个人配置、密钥、缓存、构建 DLL、完整运行日志不提交。`.env.example` 仅保留空密钥项及示例路径。生成的 reference JSON 按原项目约定保留；MIT、MinHook/HDE 和 yyjson 许可证原样保留。

## 校验与交付

创建前以认证账号 `1850VV` 查询同名仓库，返回 HTTP 404。创建方式必须为 private 空仓库，不自动初始化 README/license。仅推送上表四个明确分支，不使用 mirror、all 或强制推送。若同名仓库已经存在，则先检查归属、隐私和历史，不覆盖。

推送后核对 GitHub private 字段、默认分支、全部远端 SHA、验证报告，再独立抓取远端发布分支复核历史媒体未上传。CI 状态按实际运行结果报告。

原准备副本已经通过 116 项 Host 单测覆盖、156 项 agent 单测、Hook 构建/native regressions 和 Ruff，失败尝试保留。本过滤发布副本的检查单独记入 [filtered-checks.json](evidence/2026-10-18/filtered-checks.json)。

本次没有启动 Warcraft、训练或压力测试。旧实机验收仍对应未改变的生产源码；旧 SHA 通过映射对应新历史，不把离线检查或过滤当作再次实机验证。VectorSession/binary observations 仍未移植。

原 wc3env、warcraftAgent、Commander 工作树和原准备副本按文件哈希、HEAD、分支及完整状态核对。保留结果在本地交付日志中。ChatGPT 审查端需具备该私有仓库读取权限。
