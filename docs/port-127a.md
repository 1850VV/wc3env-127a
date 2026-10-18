# Warcraft III 1.27a 移植与验收

本分支已把正式 `WC3Env`、`GameSession`、`PlayerView`、`StepPool` 后端迁移到本机 Warcraft III 1.27a。下列验收使用真实游戏进程，不把 mock、静态反汇编或接口返回成功当作游戏执行证据。

功能清单、接口用法和 Python 示例见 [1.27a 功能说明](features-127a.md)。

工作目录：`C:\Users\vvv\Documents\ChatGPT\wc3env-127a`，分支 `codex/wc3-127a`。
原 `warcraftAgent` MVP、AMAI 地图和原游戏安装目录未修改。

## 为什么此前的移植没有完成

1. 原实现绑定 1.29 的 EXE，而 1.27a 的引擎在启动后才加载的 `Game.dll` 中。只改版本号或哈希无法移植。
2. 对象布局和调用约定不同：对象类型从 `+0x34` 变为 `+0x30`；对象枚举、句柄解析采用 fastcall；位置读取的两个调用共享栈参数，不能拆成两个普通函数调用。
3. 时钟、25 ms 游戏更新、离线包生产器、玩家命令身份和录像字段都需要重新绑定。探针能移动一个单位，不代表正式接口已经支持完整游戏。
4. 开局配置一度把玩家槽位状态误当成控制者类型检查，导致本地玩家被改成电脑；现已修复并通过原始建筑与控制测试。
5. 旧测试假设固定出生方向、建筑坐标与很短的战争迷雾刷新时间，旧录像也是 1.29 文件。现在使用观测到的出生点、有效建筑位置、明确的场景前置条件及现场录制的 1.27a 录像。

## 支持的精确二进制

两份文件都必须为 x86/PE32、版本 `1.27.0.52240`，且 SHA-256 完全匹配。校验在创建游戏进程前完成。

| 文件 | SHA-256 |
|---|---|
| War3.exe | ea8f5192efede23f84bc60140c2d4a0085ea68b86f430c1d60c354a555922def |
| Game.dll | e04d1716603c075eb0c8e1e21cf1093a664adc5249efab396bfa08d7b09d0c3a |

启动器先安装进程隔离、窗口与音频 API hooks，等待 `Game.dll` 出现后安装引擎 hooks，再开放 RPC。每次启动复制独立运行目录，保存自己的地图、录像、日志和 hook DLL；同卷 MPQ 使用硬链接。所有进程通过创建时保留的句柄关闭，不按进程名终止游戏。

## 验收证据（2026-09-27）

| 目标 | 真实验证与证据 |
|---|---|
| 完整状态与事件 | 自有/可见单位、战争迷雾、资源、比分、物品、技能、生产队列、建筑、内部单位、事件独立消费；`runs/formal-e2e-final.log` |
| 动作实际执行 | 移动、停止、攻击、采集、建造、训练、研究、技能、物品、复活与献祭；检查位置、生命/法力、订单、产生单位和事件 |
| 精确步进与加速 | 25 ms 步进，1/64/256/2048 倍速度、多次重置、6000 ms 正常速度墙钟检查；`tests.e2e.test_clock` |
| 玩家与多进程 | 四种族、种子、随机出生点、4/8 玩家、多实例池、独立目录、断开与关闭；主 E2E 全部 12 个模块通过 |
| AI 与画面 | 三种原生 AI 难度、AI 控制的 agent 槽位、Direct3D 9 呈现开关及原生屏幕文字；`runs/formal-runtime-extra-final.log` 两项真机测试通过 |
| 录像 | 现场录制的双方移动、建筑及战斗录像逐样本匹配；EOF 不伪造胜负，重置使用新进程 |
| 完整离线比赛 | 原生 AI 打完比赛；重载及换进程的完整状态序列和结果一致；扩展 determinism 模块通过 |
| 多地图确定性 | Echo Isles 暗夜/不死、Secret Valley 兽族/人族、Twisted Meadows 四族/多电脑，三组各重复两次；`runs/formal-extended.log` |
| 大规模状态/控制 | 2,048 个额外飞行单位，渲染开关两种模式下完整观测、精确推进并控制最后一个单位；无需旧版 allocator 补丁 |
| 连续生命周期 | 64 轮 session reset，保留默认 32 轮进程回收策略；`runs/compatibility-127a-soak.json`，85.7 秒完成 |
| 四族与特殊场景 | 主场景 4/4；修复后完整扩展场景 16/16，含经济、生产、建筑队列、施法拒绝、英雄复活、商店及酒馆；`runs/formal-extended-scenarios-release.log`，所有场景零意外拒绝动作 |
| 静态资料 | 从本机 1.27a 重新提取 836 单位、799 技能、273 物品、89 科技、237 buff 与 Echo Isles 地图；保留稳定英文命令名，修复 UTF-8 中文提取 |
| 独立安装包 | wheel 在全新虚拟环境中安装，离开源码导入路径后加载；真实游戏移动 134.84 单位距离、连续四次 250 ms 步进及同进程重置通过；`runs/formal-wheel-check.log` 与 `runs/formal-wheel-live.log` |
| 仓库检查 | 环境配置后主机单测 107/107、agent 单测 156/156；原生 JSON/时钟/allocator 回归、Ruff lint/format 与修改过的 C/H 的 clang-format 检查通过 |

本机测试覆盖 Windows 和 Direct3D 9。其他补丁、Linux/Wine、其他图形后端与任意修改地图的行为未由这些结果证明。LAN/在线对战不属于该离线 API。

## 安装产物

本地安装包：`dist/wc3env-0.1.0+wc3127a-py3-none-win_amd64.whl`，包含已编译的 x86 hook DLL，不包含游戏文件。可在 Windows x64、Python 3.11+ 环境安装：

SHA-256：`4c7aa8521a0eb85f84760631f37e67d1922359001e25a3a68ba5064da3be96d2`。

```powershell
python -m pip install 'dist/wc3env-0.1.0+wc3127a-py3-none-win_amd64.whl'
$env:WC3_GAME_DIR='G:\war3\Warcraft III Frozen Throne 1.27a publish'
python -m wc3env --instances 1 --steps 20 --speed 64
```

源码目录的本机 `.env` 已配置安装目录和隔离输出目录，可直接运行上述 CLI。此文件不提交到仓库。

## 复现

```powershell
$env:WC3_GAME_DIR='G:\war3\Warcraft III Frozen Throne 1.27a publish'
$env:WC3_OUTPUT_DIR='G:\war3\wc3env-127a-runs\formal'
$env:WC3_SOUND='0'
wc3hook/build.bat
.venv/Scripts/python -m unittest discover -s tests/unit -t .
.venv/Scripts/python -m unittest discover -s wc3agent/tests
.venv/Scripts/python -m tests.e2e
.venv/Scripts/python -m tests.e2e.extended
.venv/Scripts/python tools/check_compatibility.py --only reset-soak --soak-resets 64 --output runs/compatibility-127a-soak.json
```

`tools/port127` 和 `probe127` 保留为研发诊断工具；公共接口不依赖探针。引擎 RVA 集中在 `wc3hook/wc3hook.h`。DLL、游戏资产、诊断日志及运行目录不提交到仓库。
