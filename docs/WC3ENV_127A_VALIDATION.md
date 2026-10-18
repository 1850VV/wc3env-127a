# wc3env 1.27a 源码找回与验证报告

> 第 1–11 节保留源码找回与实机验证记录，第 12 节是审批前准备记录。用户批准方案 B 后的最新发布状态见第 13 节、[同步记录](SYNC_PLAN.md)及[旧新 SHA 映射](HISTORY_REWRITE.md)。此前的浅仓库、待批准和保留历史媒体描述不代表最终发布方案。GitHub 精简证据见 [evidence/2026-10-18](evidence/2026-10-18/README.md)，原始 runs 日志不上传。

审计日期：2026-10-18（Asia/Shanghai）。结果：**已找到真实移植源码；本轮最小实机验证的 8 项核心能力全部 PASS。**

可作为本机离线「魔兽指挥官」的底层运行环境候选。尚不能称为最新版上游的完整移植，也不能据此认定指挥官完整产品、AMAI/OpenWar3AI 整合已经验收。

## 1. 项目定位与搜索范围

完整源码工作树：`C:\Users\vvv\Documents\ChatGPT\wc3env-127a`。

这是独立 **wc3env Git 仓库的 linked worktree**。其 Git 公共目录位于：

`C:\Users\vvv\Documents\ChatGPT\warcraftAgent\external\wc3env-src\.git`

因此，即使该路径在 warcraftAgent 目录内部，它也不是 `1850VV/warcraftAgent` 的普通子目录提交；仅检查后者的 GitHub 页面找不到移植实现是符合当前状态的。

| 位置 | 实际发现 |
|---|---|
| 当前 warcraftAgent 的 Wiki、能力注册、关联仓库 | `native-env` 明确指向上述工作树及原始实机日志 |
| `warcraftAgent\external\wc3env-src` | 同一 wc3env 仓库的原始 main 工作树，HEAD `2f7ddf1` |
| `Z:\Dev\Projects\war3 commander\wc3env-127a` | 无 `.git` 的 SDK 子集副本；158 个比较文件与完整工作树逐字节相同，0 个不同，完整工作树另有237个受控文件未复制；不含完整文档、单测、wc3agent、Git 历史与发布配置，不作为权威源码 |
| `Z:\Dev\Projects\war3 commander\repo` | `1850VV/warcraft-commander` 工作树，`codex/native-readiness`，HEAD `1e29857`；已有大量未提交原生恢复改动，本轮只读 |
| `C:\Users\vvv\Documents\ChatGPT\warcraft-commander`、`warcraft-commander-publish` | 另两份主产品工作树；没有把它们与 SDK 合并 |
| Codex 记录 | 工作树登记、`.codex-global-state.json` 中的相关路径、只读 `state_5.sqlite` 的项目路径；项目会话索引定位了历史移植对话 `01a0e148-d03e-7f72-8e1f-5b754415527c` |

有界目录扫描：ChatGPT 根目录深2层（82目录）、`Z:\Dev` 深3层（264）、Documents\Codex 深3层（229）、`S:\Dev\Projects` 深2层（255）、`.codex\worktrees` 深3层（10）。另外检查用户的 `source / Dev / Projects` 和 `C:\Dev / C:\Projects`，这些路径不存在。Z盘顶层检查后只深入开发目录；排除模型、权重、素材、依赖、构建产物、系统目录，未全盘递归。

主要定位命令包括 `Get-ChildItem Z:/ -Directory`、`Get-ChildItem Z:/Dev -Directory -Depth 2`、`python scripts/knowledge.py show native-env`、`git worktree list --porcelain`，随后按声明深度枚举并对候选 SDK 内容做 SHA-256 比较。

完整路径、排除规则、扫描计数、Codex项目元数据和副本差异清单见 [discovery.json](../runs/recovery-20261018-01/discovery.json)。未读取或使用凭据文件内容。

## 2. Git 与 GitHub 同步状态

| 项目 | 当前实测 |
|---|---|
| 当前分支 | `codex/archmage-kiting-mvp` |
| 当前 HEAD | `85fcefdf1f9019dd92a40e109d544ec656d0d158` |
| 1.27a 移植提交 | `dc2ca7bd17d332b3b31355fe087c5cc1a5b340e1`，`Port native Warcraft III backend to 1.27a` |
| 保留的移植分支 | `codex/wc3-127a` → `dc2ca7b` |
| 后续本地提交 | `85fcefd`：大法师风筝与步兵围杀 MVP |
| 原始移植基线 | `2f7ddf1639fc038691ff0bd20403b11e5a97497d` |
| 远程 origin | <https://github.com/pwang724/wc3env.git>，仍为原作者仓库 |
| Git 历史边界 | 当前是 shallow repository；`git log -10` 只显示可用的3个提交，不代表上游只有3个提交 |
| 调查开始时已有修改 | `M README.md`、`M docs/port-127a.md`、`?? docs/features-127a.md`；全部保留 |
| 本轮新增 | 本报告、`tools/validate_127a_recovery.py`、`tools/validate_127a_native.py`；日志与隔离构建均在忽略的 runs/ 内 |

已实际执行并保存 `git status --short`、`git remote -v`、`git branch -avv`、`git log -10 --oneline`、worktree列表、未提交diff及本地未在远程引用中的提交；见 [Git 状态](../runs/recovery-20261018-01/git-status.log)、[分支](../runs/recovery-20261018-01/git-branches.log)、[日志](../runs/recovery-20261018-01/git-log.log)、[本地提交](../runs/recovery-20261018-01/git-local-commits.log)。GitHub操作前确认了仓库、分支、remote，以及 `gh auth status` 的1850VV登录状态。

远程实查结论：

- `git ls-remote` 首次发生 Schannel TLS 握手失败；仅对该命令使用 `git -c http.sslBackend=openssl ls-remote --heads origin` 后成功，未修改Git全局配置、未关闭证书验证。
- 上游实时 main 为 **`d45a7b52c4aef0876d983f09e518115e8ac940b3`**；本地 `origin/main=2f7ddf1` 已过期。没有 fetch/rebase/merge 改变引用或工作树。
- `gh api repos/pwang724/wc3env/commits/dc2ca7b...` 返回422：没有该SHA。你的 warcraftAgent、warcraft-commander 对同一SHA的查询也未找到。
- `gh repo list 1850VV --limit 1000` 未发现 wc3env 专属仓库；直接查询 `1850VV/wc3env` 返回404。
- 当前 `warcraftAgent` 远程分支为 `codex/mvp-combat-loop`（`c66c6e0`）；完整树查询无 wc3env/wc3hook 实现。warcraft-commander main（`1e29857`）有消费者脚本，但没有 SDK 原生实现。树查询都为 `truncated=false`。

**1.27a核心改动已在本地提交；在本轮可访问的上述GitHub仓库中未同步。** 该结论不外推到未知账户、隐藏仓库或别名归档。

## 3. 1.27a 技术实现与原版差异

这不是仅修改版本字符串，也不是JASS语音桥。原生层主要是 **C / x86内联汇编 / MSVC / MinHook**，文件后缀为`.c`，不应因任务使用“C++ Hook”一词而误判它缺少原生实现。

相对移植基线`2f7ddf1`，核心提交修改64个文件，新增6520行、删除4208行；见 [差异统计](../runs/recovery-20261018-01/git-port-diff.log)。

| 领域 | 真实代码与适配 | 当前判定 |
|---|---|---|
| 二进制检测 | `src/wc3env/compatibility.py` 校验PE32/x86与两个完整SHA-256；启动前拒绝不匹配版本 | PASS：本机匹配 |
| 注入与启动时序 | `inject.py` 暂停创建进程、LoadLibraryW注入；要求DLL导出`WC3Adapter127`；`main.c`先装隔离API hooks，再拦截LoadLibraryA等待Game.dll，切换引擎基址 | PASS：本轮新编译DLL实际启动、RPC就绪 |
| 内存地址与ABI | `wc3hook.h`集中1.27a Game.dll RVA；`objects127.c/h`处理fastcall、id/salt、单位rawcode `+0x30`；位置读取保留共享栈参数的完整调用序列 | PASS：位置/HP/单位类型实测；不是沿用1.29的`+0x34` |
| Native提取 | `tools/natives.py`区分1.29栈参数注册与1.27a ECX/EDX+prototype注册；保留重复来源 | PASS：相关主机单测；本轮未重新全量提取参考资料 |
| 状态采集 | `observe.c`、`metadata.c`、`objects127.c`读取真实单位、建筑、资源、坐标、命令、生产、可见对象和inside单位 | PASS：最小核心字段；其余见历史证据 |
| Python SDK | `protocol.py`、`rpc.py`、`pipe.py`用命名管道JSON RPC；`Action`/`Observation`做类型及所有权校验 | PASS：公共API驱动真实游戏 |
| 动作 | `act.c`通过原生命令打包/离线回环投递，`placement.c`为1.27a原生摆位搜索；ACK只说明排队 | PASS：本轮移动/攻击/精确点建造实际效果；本轮未复测auto_place |
| 事件 | `events.c`绑定1.27a分发/注册/施法路径；每观察者事件游标和有界保留 | PASS：本轮建筑开工/完工；其他事件完整性本轮NOT RUN |
| 时间控制 | `clock.c`虚拟化QPC/GetTickCount/FILETIME/rdtsc；`step.c`控制25ms更新和离线包预算 | PASS：暂停、25ms推进、双实例独立时钟；加速样本见下文 |
| 生命周期 | `GameSession`与native reset调用`RestartGame(false)`，清理订单/事件/TLS等；默认每32局回收进程 | PASS：同进程重置及强制2局后换进程的既有回归 |
| 多实例 | `runtime.py`复制EXE/DLL、同卷硬链接只读MPQ；隔离地图、Replay、Save、日志和命名对象；`pool.py`并行驱动 | PASS：两个独立PID/目录/时钟 |
| 旧版专用实现 | 1.29的allocator/UI teardown补丁没有在1.27a正式启动路径安装；`tools/natives.py`仍保留1.29解析分支用于研究兼容 | 不是当前后端错误复用 |
| 遗留文档 | `wc3hook.h:1`仍写1.29.2；其建筑搜索声明附近仍写1.29；`docs/roadmap.md`的Wine旧说明与1.27a兼容文档有冲突 | 已记录，未改核心Hook；以实际代码和本轮证据为准 |

本机游戏：`G:\war3\Warcraft III Frozen Throne 1.27a publish`。

| 文件 | 本轮SHA-256（与源码要求一致） |
|---|---|
| War3.exe | `ea8f5192efede23f84bc60140c2d4a0085ea68b86f430c1d60c354a555922def` |
| Game.dll | `e04d1716603c075eb0c8e1e21cf1093a664adc5249efab396bfa08d7b09d0c3a` |

这是精确`1.27.0.52240`二进制配置，不表示任意标为“1.27a”的修改客户端都适用。

### 与2026-10-18上游最新版的区别

另外通过gh读取固定上游`d45a7b5`的README、`vector.py`、`session.py`及目录树，未把最新上游内容合并进本地：

- 最新上游确有`wc3env.vector.VectorSession`，提供worker进程、异步`send/recv`、终局自动reset、远程/Wine workers。
- 最新上游新增`GameConfig(observation="binary")`、`binary.py`和共享内存观测；本地仍为JSON接口。
- **这些新增功能尚未移植到本地1.27a。** 本地多实例可用不等价于VectorSession API兼容，更不代表上游大规模RL吞吐适用于此分支。
- 对比基线与最新上游的边界不同：旧基线本身没有VectorSession；它不是此前移植遗漏的同名类，但现在确实构成版本差距。

来源：[上游VectorSession](https://github.com/pwang724/wc3env/blob/d45a7b52c4aef0876d983f09e518115e8ac940b3/src/wc3env/vector.py)、[上游GameSession](https://github.com/pwang724/wc3env/blob/d45a7b52c4aef0876d983f09e518115e8ac940b3/src/wc3env/session.py)；本地抓取记录在`runs/recovery-20261018-01/upstream-current-*.log`。

## 4. 本轮自动化检查与最小实机验证

所有新日志根目录：`C:\Users\vvv\Documents\ChatGPT\wc3env-127a\runs\recovery-20261018-01`。

隔离游戏运行目录：`G:\war3\wc3env-127a-runs\recovery-20261018-01`。每次启动创建独立子目录；没有接管其他游戏。没有录制屏幕视频、长时间压力测试或强化学习训练。

### 自动化检查

| 检查 | 结果 | 证据 |
|---|---|---|
| `python -m unittest discover -s tests/unit -t .` | PASS，116项 | [host-unit.log](../runs/recovery-20261018-01/host-unit.log) |
| `python -m unittest discover -s wc3agent/tests` | PASS，156项 | [agent-unit.log](../runs/recovery-20261018-01/agent-unit.log) |
| 复制源码至独立build-source后执行原`wc3hook/build.bat` | PASS，x86 DLL编译及Native JSON/clock/allocator回归 | [native-build.log](../runs/recovery-20261018-01/native-build.log) |
| `python -m ruff check .` | 初次FAIL：新增审计脚本的UP017；已只修正新增脚本，最终PASS | [原失败](../runs/recovery-20261018-01/ruff-check.log)、[最终](../runs/recovery-20261018-01/lint-final.log) |
| `python -m ruff format --check .` | PASS | [format-final.log](../runs/recovery-20261018-01/format-final.log) |
| 当前warcraftAgent仓库要求的`powershell -NoProfile -File scripts/test.ps1` | 首次被本机执行策略阻止；仅对新PowerShell进程加`-ExecutionPolicy Bypass`后PASS，1006项测试、地图/语音包构建及独立解析通过 | [初次阻止](../runs/recovery-20261018-01/warcraftAgent-required-tests.log)、[最终日志](../runs/recovery-20261018-01/warcraftAgent-required-tests-r2.log) |
| Wiki/能力注册证据核验 | PASS；更新仅涉及本轮定位、状态与证据链接 | [wiki-registry-check.json](../runs/recovery-20261018-01/wiki-registry-check.json) |
| 新增审计脚本退出码及报告链接 | PASS：正常子命令返回0，失败子命令7原样传播；本地链接存在 | [delivery-check.json](../runs/recovery-20261018-01/delivery-check.json) |

这些是主机/构建检查，不算实机能力通过。未安装任何依赖；使用已有`.venv` Python 3.12.10和MSVC。没有更改持久化PowerShell策略。原Lua/Reforged MVP的游戏验收仍为NOT RUN，与本轮1.27a原生测试分开。

### 8项核心能力（本轮真实游戏）

| # | 验证项 | 状态 | 观察到的证据 |
|---|---|---|---|
| 1 | Python连接游戏 | PASS | 公共`GameSession.reset()`成功，PID12896，原生RPC返回真实初始状态 |
| 2 | 读取单位位置、血量和资源 | PASS | 5农民+主基地；农民HP220，初始金500/木150、人口5/12；完整单位位置和RPC元数据已保存 |
| 3 | 发出移动、攻击、建造 | PASS | 三类Action经正常命令路径下发；使用启动农民移动/造农场；战斗对象由debug spawn显式布置 |
| 4 | 命令实际执行 | PASS | 农民位移409.912；敌步兵HP420→355；农场HP500、state=null，construct_start与construct_finish均出现；金木500/150→420/130，人口上限12→18 |
| 5 | reset重置 | PASS | PID12896保持不变；变动后的地图重载至1.0秒、500金150木、5农民+主基地；比较规范化初始状态一致 |
| 6 | step推进 | PASS | `step(ms=25)`从1.000→1.025秒；双实例随后各4次250ms均精确完成 |
| 7 | 同条件复现 | PASS（限定夹具） | 既有native测试固定seed21，3轮32点战斗HP轨迹/初始种族和位置一致；前两轮同进程，第三轮换进程；不是任意地图/全对局确定性的重新验收 |
| 8 | 两个独立实例 | PASS | StepPool：兽族seed31与不死seed73，PID29504/15200；不同目录；只推进实例0后时间为1.25/1.00，随后并发4轮后2.25/2.00 |

最终实机过程约25.89秒墙钟。证据：[机器结果](../runs/recovery-20261018-01/native-r2/result.json)、[完整命令/观测流](../runs/recovery-20261018-01/native-r2/trace.jsonl)、[执行日志](../runs/recovery-20261018-01/native-minimal-r2.log)。攻击测试没有调用debug damage或修改目标HP；这里用真实HP下降证明伤害，未把`attacked`事件当作逐次伤害或死亡证明。

暂停PASS：步进间等待0.3秒墙钟，游戏时间仍为1.0。加速参数可设置：本轮1倍和64倍各推进1秒模拟时间，调用墙钟分别约0.261/0.114秒。这个短样本只表明配置和执行路径工作，**不证明精确64倍吞吐，也不标定“1倍=真实墙钟”**；长期吞吐本轮NOT RUN。

### 失败记录与未执行范围

第一轮新增验证脚本完成连接/读取/移动/建造/攻击/reset后，在导入既有测试时发生`ModuleNotFoundError: No module named 'tests'`。属于直接运行tools脚本的sys.path问题，未修改SDK或Hook。原始 [result.json](../runs/recovery-20261018-01/native/result.json) 和 [日志](../runs/recovery-20261018-01/native-minimal.log) 保留为FAIL；修正新增脚本后在全新输出目录完成第二轮。

大规模RL训练、64轮soak、2048单位压力、全场比赛、多地图确定性、录像回放、完整AMAI/Commander操作、OpenWar3AI同场整合、Linux/Wine：**本轮NOT RUN**。

## 5. reset / step / VectorSession 的实际状态

| 接口 | 实际语义 | 状态 |
|---|---|---|
| `GameSession` | 一场游戏/一个模拟时钟，支持多玩家合并动作；`reset()`返回按玩家索引的观测；`step(actions, ms)`返回`observations, done, info` | PASS |
| `WC3Env` | 单agent包装；`reset()`返回单观察者字典；`step(actions, seconds)`返回3项，无内置reward | 已有实现；本轮主要测底层GameSession，历史WC3Env实机证据存在 |
| native reset | 重新加载当前地图，不是保存/恢复任意中局快照；1秒启动hold；默认32局后回收；故障与录像重置有换进程路径 | PASS：同进程+回收夹具；故障/录像恢复本轮NOT RUN |
| step | 25ms整数倍，25..60000ms；先提交所有玩家动作，再推进一次，最后观察；realtime模式语义不同 | PASS：本轮stepping模式；realtime本轮NOT RUN |
| `StepPool` | 多独立游戏进程，每个一个驱动线程，按一轮并行等待；不是最新上游异步RL向量会话 | PASS：2实例 |
| `VectorSession` | 本地不存在`src/wc3env/vector.py`，没有对应导出；最新版上游的worker/send/recv接口未移植 | FAIL（接口缺失） |
| 二进制共享内存观测 | 本地没有binary.py及对应配置 | FAIL（功能缺失） |

本地不提供标准Gymnasium五元组、内置奖励函数、神经网络训练器或任意时刻状态分叉。需要时在外围增加适配，不应把已有reset或StepPool解释成这些能力。

## 6. 历史证据复核与仍未实现部分

本轮回读并计算SHA，确认历史证据仍在：

- `runs/formal-e2e-final.log`：12/12模块、4/4场景；SHA `6cbc9701b6eab34f6ddac68a86fdf4191ec77e442caa95795e9442aa13cea12f`。
- `runs/formal-extended-scenarios-release.log`：16/16扩展场景；`formal-runtime-extra-final.log`：原生AI/呈现2项通过。
- `runs/compatibility-127a-soak.json`：历史64次reset；SHA `9bb611dbc79fd959b6a1fc48f766eb372784ce302650daaab3a241f865584a23`。
- `runs/formal-wheel-check.log`、`formal-wheel-live.log`：历史独立wheel安装、实机移动/重置。
- `runs/features-127a-doc-check.log`：历史三个文档示例实机通过。

这些支持历史完成度，不能改写为2026-10-18重新运行了全部测试。

当前明确缺口：VectorSession、binary observations及其新RL协议；任意中局快照恢复；通用奖励/训练；在线/LAN API；无窗口渲染。Shift队列中后续未开始的建筑占地没有完整保留；新增槽位`players[].team=-1`仍需处理。其他补丁、图形后端及Wine的1.27a兼容性UNKNOWN/NOT RUN。

## 7. 最严重技术风险

1. **版本与来源分散。** 完整实现仅在一个浅Git仓库/工作树，远程指向别人；Z盘是没有历史/完整测试的子集副本。上游又增加了VectorSession/binary等API。应先固定可复现源码、构建指纹及兼容矩阵，避免消费端误装最新版上游或只复制若干文件。
2. **SDK与指挥官扩展DLL并非同一契约。** 指挥官现有`panel-hook.dll`还包含地图/面板/CommandAI等扩展，本轮测试的是未修改核心的SDK DLL。基础SDK通过不能证明随意替换扩展DLL或完整指挥官流程通过。
3. **观测证据精度。** 基础`observe.c`把HP/法力输出为整数；小数HP可能截断为0。没有逐次damage/projectile-release通用事件；`attacked`不是弹丸发射或伤害。必须用独立death事件证明死亡；微操的精确伤害/发射时刻需已有专用扩展或后续审计。
4. **生命周期与吞吐边界。** reset会清空游戏状态而不是分叉；默认32局换进程不可随意取消。render=False仍使用D3D9窗口/设备。本轮2实例和短夹具不代表大规模吞吐/稳定性。
5. **动作仲裁。** ACK只代表排队；AMAI、人类和确定性微操若同时给同一单位下令会互相覆盖。需要所有权、优先级、租约到期和人工接管流程。

## 8. AMAI 与 OpenWar3AI 整合建议

### AMAI

[AMAI官方版本表](https://github.com/SMUnlimited/AMAI)将TFT脚本的最佳范围列为1.24–1.28，适合作为1.27a宏观规则参考。沿用主项目已经固定的`de97faeb73c420d165bd9eaf8a4c7e19e0a1bb15`及TFT构建来源，不随意升级。

优先复用已有`build_commander_assets.py`的隔离扩展与`CommandAI`入口，SDK负责进程、状态、动作、时间；AMAI负责指定电脑槽位的宏观。先做独立盟友命令的实际效果验收，再增加控制权交接。当前`effect_observed=False`的回执应保持原意，不能显示为任务完成。AMAI整合本轮NOT RUN。

### OpenWar3AI

本轮读取[固定提交ffd7dd2的README](https://github.com/OPENXXAI/OpenWar3AI/blob/ffd7dd25a3c2478f457b74bde89d23e605b24243/README.md)。其自述为1.27a注入runtime、共享内存和Python SDK，公开源码为Apache-2.0，而prebuilt原生runtime不提供源码且另有使用条款；此处是来源审计，未安装或验证其运行能力。

建议把它作为可选独立后端，在指挥官外围定义统一Observation/Action/receipt接口；不要直接同时向一场游戏注入两个runtime。它的全图状态与wc3env按观察者视野过滤的语义不同，必须在适配层明确过滤。仲裁、UI和网关可作为架构参考，原生二进制不应当作可直接合并的开源Hook。跨后端确定性/单位ID/错误语义均需单独验证，本轮NOT RUN。

## 9. 接入 warcraft-commander 的最小改动方案

当前Z盘主项目已经有未提交的`local_paths.py`、`check_native_ready.py`、`native-setup.md`和原生消费者；本轮没有改动或覆盖它们。

1. 后续获准接入时，将其忽略配置`.local/native-paths.json`中的`WC3_SDK_ROOT`指向完整审计工作树，或指向从专属仓库检出的固定版本。现有配置仅指定游戏路径，所以SDK默认落到相邻Z盘子集。先运行已有`check_native_ready.py`；路径检查通过只算OFFLINE_READY。
2. 保持产品代码与SDK分仓。`strategy_panel_native.py`已有HookPipe/RpcClient入口；自动化独立测试使用GameSession，人工选图模式保留现有手动启动/连接流程，不能强行用reset接管用户对局。
3. 用固定SDK源码构建现有独立Commander扩展DLL，记录SDK commit、源码hash、扩展DLL hash、游戏/地图hash。继续使用主项目已有的地图、导航和AMAI输入来源；缺失时报告缺失，不伪造替代布局。
4. 给现有动作回执补充效果判据：位移、目标HP变化、建筑开工/完工、资源/人口变化和单位死亡事件。高频控制保持确定性，LLM/语音只产生低频战略目标。
5. 最小接入验收只需一局：手动选图后连接，读取资源/坐标，移动一个农民、建造一座农场并观察完工，停止/断开时不关闭用户游戏。AMAI命令另作独立验收。无需先实现VectorSession。

该方案本轮未实施；本轮原生验证使用独立stock Echo Isles测试进程。

## 10. 同步安全与下一阶段工程任务

**可以整理为可同步的源码变更，但当前不应无审查地整目录打包上传。没有创建仓库、提交、推送、覆盖分支或修改远程。**

建议经用户批准后创建独立私有`1850VV/wc3env-127a`（或按用户要求建立fork），`upstream`保留pwang724，`origin`为自己的仓库。保留`codex/wc3-127a`的原始移植提交和`codex/archmage-kiting-mvp`的后续实验历史；在新的`codex/127a-validation`评审分支整理本轮脚本/报告与原有未提交功能文档，验证后再决定稳定分支。不要将当前主产品或warcraftAgent当作SDK同一仓库。

待同步内容：本地移植`dc2ca7b`、按需保留的`85fcefd`、原有README/port文档修改与未跟踪`features-127a.md`、本轮报告和2个独立验证脚本。

初步受控文件清单未发现游戏EXE/DLL/MPQ/地图、`.env`或凭据文件；`.env`、runs/和构建DLL被忽略。但仓库已跟踪`tests/fixtures/combat.w3g`、`self_play.w3g`及生成的`wc3agent/.../reference.json`，同步前应核查来源、个人标识和分发范围。此清单检查不是完整Git历史的敏感信息审计。运行目录、游戏安装、私有地图、凭据和完整机器日志不进入同步。见 [sync-inventory.json](../runs/recovery-20261018-01/sync-inventory.json)。

下一阶段最重要的三项任务：

1. **整理并备份SDK专属源码仓库。** 用户批准后完成敏感/资产清单审查、保留上游许可证及本地提交，形成固定版本和构建指纹；再同步，不混入游戏文件。
2. **接通现有指挥官原生路径并做一局端到端验收。** 固定SDK来源，重用现有扩展构建与手动生命周期，验收真实读取→移动→建造→事件回写→安全断开。
3. **明确后续接口差距。** 若需要RL，再单列VectorSession/binary移植；若优先可玩指挥官，先完成AMAI命令效果与控制权仲裁、HP精度/死亡证据问题。不得直接套用上游1.29地址或把本次通过等同于已可大规模训练。

## 11. 执行命令、产物与保留核验

关键命令（从完整SDK目录运行；日志内的`*.command.json`记录实际argv、cwd、UTC时间、退出码和墙钟）：

```powershell
.venv/Scripts/python tools/validate_127a_recovery.py snapshot --output runs/recovery-20261018-01
.venv/Scripts/python tools/validate_127a_recovery.py offline --output runs/recovery-20261018-01
.venv/Scripts/python tools/validate_127a_recovery.py build --output runs/recovery-20261018-01
$env:WC3_HOOK_DLL=(Resolve-Path runs/recovery-20261018-01/build-source/src/wc3env/native/wc3hook.dll).Path
$env:WC3_OUTPUT_DIR='G:/war3/wc3env-127a-runs/recovery-20261018-01'
.venv/Scripts/python tools/validate_127a_recovery.py command --output runs/recovery-20261018-01 --label native-minimal-r2 --timeout 240 --command .venv/Scripts/python tools/validate_127a_native.py --output runs/recovery-20261018-01/native-r2 --runtime G:/war3/wc3env-127a-runs/recovery-20261018-01
.venv/Scripts/python tools/validate_127a_recovery.py preserve --output runs/recovery-20261018-01
```

复现时必须换新的输出目录和label；工具拒绝覆盖已有命令日志和native输出目录。构建脚本只在复制出的`build-source`中运行；本轮实机使用该新DLL，SHA-256 `6f11053251f18deaba2e0af2baf4a2faeba8c93a372734b91b8493966d0f3b87`。原工作树已有DLL保持原hash `8ca108ef54703fa645a1004e9a7902ea80199a8ccb2c66b4f0afc961930c4ae4`。

[preservation.json](../runs/recovery-20261018-01/preservation.json)：396个原有受控源码文件与391个游戏二进制/MPQ/地图文件哈希均未改变。原有未提交文档修改保留。本轮结束后无Warcraft游戏进程残留；没有关闭其他用户游戏。完整日志、原失败和所有隔离运行目录均保留。

按当前项目知识维护要求，另外增量更新了`warcraftAgent/docs/wiki/control-and-environment.md`、`docs/wiki/feature-map.md`和`knowledge/capabilities.json`，更新前原文保存在本轮证据目录的`wiki-before/`。没有改写冻结训练数据或历史验收结果。

## 12. 独立私有仓库准备补充（2026-10-18）

本节仅记录后续的同步准备，不将上一轮游戏结果算作再次运行。新的独立发布副本为 `C:\Users\vvv\Documents\ChatGPT\wc3env-127a-publish`，使用独立 `.git`，不再依赖 warcraftAgent 下的 Git 公共目录。分支为 `codex/127a-private-sync`，基准仍为 `85fcefdf1f9019dd92a40e109d544ec656d0d158`；尚未新建提交。补齐上游历史后，4 个原有提交及其父关系完整保留，仓库不再是浅克隆。

使用已认证的 `1850VV` 查询 `repos/1850VV/wc3env-127a` 返回 HTTP 404；本次没有创建 GitHub 仓库、推送或修改原项目。拟议目标为独立私有仓库，`upstream` 指向原作者；创建和推送仍等待用户批准。

已整理上游/第三方许可证、1.27a 技术说明、API 兼容表、功能说明、两个独立验证脚本、本文及可分享的派生证据。源码目录结构保持不变，生产 Python/C Hook 源码保持原样。

当前树拟删除 12 个上游演示媒体文件和 2 个过时回放文件。审计发现两个回放都为上游原样的 1.29/build 6060，不能通过本项目 1.27 回放解析器；当前 native replay 测试使用临时录制，不依赖这两个旧文件。删除仅作用于发布副本。**保留原提交历史意味着这 14 个历史二进制对象仍会随推送上传**（媒体 116,660,027 字节，回放 4,825 字节）。是否允许此历史例外必须纳入审批；严格从全部历史排除它们会改变提交 SHA，本次没有改写历史。

历史扫描覆盖 425 个 blob（411 个文本、14 个上述二进制），未命中规则匹配的密钥或游戏安装文件路径。该扫描不是任意敏感内容不存在的数学证明。`.env`、密钥、地图、游戏 EXE/DLL/MPQ、构建缓存、本地日志及个人配置均排除；生成的 reference JSON 按项目约定保留。

发布副本离线验收：Host 共 116 项单测覆盖 PASS（discovery 记录 114 条，其中 113 通过、1 个模块因导入时的游戏路径检查跳过；随后仅通过进程环境提供现有安装路径，该模块的 3 项合成单测单独通过，未启动游戏）；agent 156 项 PASS；独立 Hook 构建及 native regressions PASS；Ruff 检查及格式检查 PASS。首两次 Host 检查因新副本缺少包内生成 DLL 而 FAIL；环境变量无法覆盖测试中的 mock settings，放置本次构建产物后通过。失败日志均保留。实机和全新 wheel 安装在本同步准备阶段均为 NOT RUN。

逐条命令、日志哈希、原始失败状态与证据边界见 [审查证据说明](evidence/2026-10-18/README.md)。拟提交文件和远端分支对应关系见 [SYNC_PLAN.md](SYNC_PLAN.md)。第 11 节提到的主项目 Wiki 更新属于上一轮验证；本次同步准备不修改 warcraftAgent 或任何 warcraft-commander 副本。

## 13. 批准方案 B 后的发布记录（2026-10-18）

用户已明确批准「按方案 B 创建并推送」，不再等待审批。实际发布目录为 `C:\Users\vvv\Documents\ChatGPT\wc3env-127a-private`，这是全新独立对象库；原准备副本与原始项目均保留。目标为独立私有仓库 [1850VV/wc3env-127a](https://github.com/1850VV/wc3env-127a)，默认分支 main，整理分支 codex/127a-private-sync。

通过现有 Git fast-export/fast-import 从四个原历史提交中排除 `docs/media/**` 与 `tests/fixtures/*.w3g`。新对象库没有 12 个上游演示媒体及 2 个旧回放的任何原二进制对象；不仅是删除当前目录。四个提交的保留文件 blob ID/模式、作者/提交者/时间、说明、映射后父关系均验证一致。两个旧 SSH 签名因 SHA 改写而移除，未冒称为新提交的有效签名。

原移植 `dc2ca7bd17d332b3b31355fe087c5cc1a5b340e1` 对应 `bad0278a39ea1b1ea1233c230677f83f5ecd86a7`；原后续 `85fcefdf1f9019dd92a40e109d544ec656d0d158` 对应 `4f2b66179fa766c9228b35990b815386d8edcf08`。完整映射见 [HISTORY_REWRITE.md](HISTORY_REWRITE.md)。此前实机证据中的旧 SHA 仍准确描述当时运行源码，通过映射关联到发布历史。

本发布副本重新执行独立 Hook 构建/native regressions、Host 116 项单测、agent 156 项单测、Ruff check/format，全部 PASS。Host 此次通过进程环境提供现有游戏安装路径，116 项无跳过；这只用于导入时的路径检查，合成单测没有启动游戏。未复制个人配置。实机、训练、压力测试与本地全新 wheel 安装本次均 NOT RUN。GitHub CI 另按远端实际状态报告。

过滤基准历史包含 411 个文本 blob，二进制 0、禁止文件路径 0、规则匹配密钥 0、旧二进制对象残留 0；没有依赖安装或核心 Hook 修改。见 [filtered-history-audit.json](evidence/2026-10-18/filtered-history-audit.json)、[history-rewrite.json](evidence/2026-10-18/history-rewrite.json) 和 [filtered-checks.json](evidence/2026-10-18/filtered-checks.json)。最终只推送过滤后的四个明确分支，并核验 private 字段、远端 SHA 和报告内容；不推送原历史备份引用。
