# wc3env 1.27a 功能说明

本文介绍已适配 Warcraft III 1.27a 的 wc3env 能做什么、如何调用，以及使用时需要遵守的接口约定。依据为分支 `codex/wc3-127a` 的实现提交 `dc2ca7b` 和 2026-09-27 的本机真机验收结果。

wc3env 为 Python 程序提供真实魔兽游戏的“读取状态 → 提交动作 → 推进时间 → 观察结果”接口。它直接读取和控制游戏引擎，使用世界坐标和对象 ID，不依赖截图识别或鼠标点击。可用于编写规则 AI、接入外部模型、批量运行离线对局，以及制作可重复的战斗和经济实验。

它提供类似 Gym 的调用方式，但没有内置奖励函数，也不直接实现 Gymnasium 的标准返回格式：`WC3Env.step()` 返回 `(observation, done, info)`。策略、奖励计算和外部 LLM 调用由上层程序负责。仓库中的 `wc3agent` 是单独的实验性策略层；wc3env 的运行不需要模型 API 密钥。

## 1. 支持环境与安装

| 项目 | 当前范围 |
|---|---|
| 游戏 | Warcraft III 1.27a，x86 构建 `1.27.0.52240` |
| 版本识别 | 启动前同时校验 `War3.exe`、`Game.dll` 的架构和完整 SHA-256；同名文件或相同版本标签不能代替二进制匹配 |
| 主机 | 本机 Windows x64；64 位 Python 3.11+，验收使用 Python 3.12 |
| 图形 | Direct3D 9；关闭画面呈现后仍需要窗口和图形设备 |
| 游戏模式 | 本地离线地图、原生电脑对手、多 agent 同局、多个独立游戏进程 |
| 安装包 | `wc3env-0.1.0+wc3127a-py3-none-win_amd64.whl`，内含 x86 hook DLL，不含游戏文件 |

精确二进制哈希和安装包校验值见[移植与验收报告](port-127a.md)。使用已构建的 wheel 无需本机安装 C++ 编译器；从源码重新构建 DLL 才需要 Visual Studio C++ Build Tools。

在仓库根目录安装并运行一个实例：

```powershell
python -m pip install 'dist/wc3env-0.1.0+wc3127a-py3-none-win_amd64.whl'
$env:WC3_GAME_DIR='G:\war3\Warcraft III Frozen Throne 1.27a publish'
$env:WC3_SOUND='0'
python -m wc3env --instances 1 --steps 20 --stepms 250 --speed 64
```

更换电脑时把 `WC3_GAME_DIR` 改为自己的游戏安装路径。当前源码目录已有本机 `.env` 配置。输出目录可通过 `WC3_OUTPUT_DIR` 或 `GameConfig(output_dir=...)` 指定。

## 2. 功能总览

| 能力 | 可以完成的工作 | 主要接口 |
|---|---|---|
| 单 agent 控制 | 启动、读取自己的视野、提交动作、推进与结束一局 | `WC3Env` |
| 多 agent 同局 | 各玩家提交自己的动作，共用一次模拟时间推进 | `GameSession`、`PlayerConfig` |
| 玩家视图 | 读取该玩家最近的缓存观测，不推进游戏或重复消费事件 | `session.view(slot)` 返回 `PlayerView` |
| 状态读取 | 资源、单位、技能、物品、生产队列、地图边界、关系和比分 | `observation` |
| 原生动作 | 移动、攻击、采集、建筑、训练、研究、施法、物品与复活 | `Action` 或动作字典 |
| 时间控制 | 25 ms 粒度的步进、连续实时运行、时钟加速 | `GameConfig`、`step()`、`debug("speed", ...)` |
| 对局配置 | 四种族、电脑难度、随机种子和出生点排列 | `PlayerConfig`、`MatchSetup` |
| 多进程并行 | 并行运行多个独立地图，统计推进量与耗时 | `StepPool`、命令行入口 |
| 生命周期 | 同进程重开、定期回收进程、故障后重建、释放实例 | `reset()`、`close()` |
| 原生录像 | 导出 `.w3g`，按步进方式回放和读取状态 | `save_replay()`、以 `.w3g` 作为 `map` |
| 实验与诊断 | 生成单位、设置资源、显示文字、读取性能数据 | `debug()`、`info`、实例日志 |

## 3. 能读取哪些状态

观测是普通 Python 字典，也可以用 `Observation.from_dict(obs)` 转为协议对象。每个配置玩家按自己的视野获得状态；读取其他配置玩家的视图需要上层实验自行确定允许的信息范围。

| 状态类别 | 主要字段与内容 |
|---|---|
| 时间与结果 | `sequence`、`game_time_seconds`、`result`；结果包括空字符串、`victory`、`defeat`、`draw` |
| 经济 | `player.gold`、`lumber`、`food_used`、`food_cap` |
| 自有单位 | `units`：ID、类型、所属玩家、位置、当前/最大生命和魔法、建筑/英雄标记、等级、buff |
| 当前命令 | 自有单位的 `order`：命令名、目标对象、目标坐标；空闲时为 `null` |
| 技能 | 自有单位的 `abilities`：技能 ID、等级、实时耗蓝、冷却总时长和剩余冷却 |
| 建筑与生产 | 建造/升级状态、`queue` 训练或研究队列、工期；`state_seconds`、`queue_seconds` 是总时长，需要结合开始事件判断进度 |
| 内部单位 | `inside`：矿内工人、建筑内单位和运输载员；它们暂时不在 `units` 中，也不能作为普通在场单位发令 |
| 可见其他单位 | `visible_enemies`：该玩家视野内其他所有者的单位，也可能包含盟友和中立单位；不披露其命令、技能列表和生产队列 |
| 地面物品与背包 | `items` 为可见存活地面物品；`inventory` 包含持有者、0–5 号槽位、类型和剩余次数 |
| 可破坏物 | `destructables`：树木等对象的位置、生命、无敌标记和 `resource` 分类；标为木材资源不保证当前单位能采集到 |
| 玩家关系 | `players`：阵营、控制者、敌友关系、共享视野和控制标记；不要仅凭槽位编号推断敌友 |
| 地图与比分 | `map.bounds` 为世界坐标边界；`score` 为观察者的 25 项原生比分计数器，包含采集、生产、击杀等 |
| 事件 | `events`、`events_lost`：该观察者自上次观测后可见的事件及溢出数量 |

buff 只提供当前 ID，不提供剩余持续时间。技能信息也不等于“当前一定能成功施放”：路径、免疫、目标类型和引擎规则仍然有效。地图世界边界不等于所有区域都可通行。

`chat` 接口还可收集可见后台窗口中本地玩家手动输入的可打印 ASCII 文字；这一人工交互行为没有作为本轮 1.27a 自动验收的独立项目。

完整字段定义见[观测协议](specs/observations.md)。

## 4. 可以下达哪些动作

每个动作包含 `unit_id`、`command`、`arguments`。`unit_id` 是本局运行时对象 ID；`type_id`、`ability_id` 通常是四字符数据 ID，例如农民 `hpea`、农场 `hhou`。

| 命令 | 功能 | 关键参数 |
|---|---|---|
| `move` | 移动到世界坐标 | `x`、`y` |
| `stop` | 停止当前命令 | 无 |
| `attack` | 攻击目标或攻击移动 | `target_id`，或 `x`、`y` |
| `smart` | 游戏右键语义：跟随、采集、拾取等 | `target_id` |
| `harvest` | 发出采集命令 | `target_id`，或 `x`、`y`；采木应明确指定树木 |
| `build` | 指定地点建造、在对象上建造、搜索附近可建位置 | `type_id` 与位置/目标；可选 `auto_place=True` |
| `train` | 训练单位或英雄 | `type_id` |
| `research` | 研究科技 | `type_id` |
| `learn` | 学习英雄技能 | `ability_id` |
| `cast` | 发出技能或特殊订单 | `order`，可选位置或目标 |
| `use_item` | 使用背包物品 | `slot`，可选位置或目标 |
| `drop_item` | 丢弃、转交物品，或交给商店出售 | `slot`，可选位置或 `target_id` |
| `select` | 选择单位 | 无 |
| `buy` | 从商店购买，以指定单位为买家 | `shop_id`、`item_type_id` |
| `revive` | 由祭坛复活自己的阵亡英雄 | 祭坛作为 `unit_id`，英雄 ID 作为 `target_id` |

`cast` 还覆盖原生特殊订单，例如地狱火、献祭和缠绕金矿。测试检查产生的地狱火、阴影或缠绕金矿；这些动作仍需满足技能、资源和目标前提。

支持 Shift 队列的命令可传 `queued=True`：`move`、`stop`、`attack`、`smart`、`harvest`、`build`、`cast`、`use_item`。普通非队列命令会替换该单位的待执行命令。训练和研究使用引擎自己的生产队列，不接受该参数。

`auto_place=True` 调用游戏的建筑选址算法，把传入坐标当作搜索锚点；解析后的坐标在 `info["placements"]` 中返回。它不会替策略挑选工人、规划分矿或自动重试失败建筑。在金矿对象上建造应使用 `target_id`，不能同时启用 `auto_place`。

`session.groups(slot)` 支持用名字保存一组自有单位，并展开成普通动作；它是 Python 分组，不是游戏中的数字快捷键编队。重置会清空分组。

### 动作成功如何判断

`info["rejected"]` 反映接口拒绝的动作，如无效单位、无权限、参数错误、找不到建筑位置等。空列表只说明动作通过了这一层校验。资源不足、前置科技、目标不可达或后续命令覆盖，仍可导致游戏不执行。

调用方应在后续观测中核对实际位置、命令、生命/魔法变化、资源变化、生产队列和事件。细节见[动作协议](specs/actions.md)。

## 5. 事件与结果追踪

| 事件类别 | 可用事件 |
|---|---|
| 战斗 | `attacked`、`death`、`spell_effect`、`summon` |
| 建筑 | `construct_start/cancel/finish`、`upgrade_start/cancel/finish` |
| 生产与科技 | `train_start/cancel/finish`、`research_start/cancel/finish` |
| 英雄 | `hero_level`、`hero_learn` |
| 物品 | `item_pickup`、`item_use`、`item_sold` |

事件保留发生时的值和可见性，每位观察者独立消费。每人最多保留最近 1,024 条可见事件；读取不及会通过 `events_lost` 报告丢失数量。不可见事件不会挤掉可见事件，隐藏的次要对象引用也不会泄露真实 ID。

`attacked` 表示受到攻击的事件，不是逐次伤害数值日志。需要量化伤害时，应结合生命变化和相应实验条件。科技完成状态可通过 `research_finish` 累积，上层应处理事件溢出情况。

## 6. 时间、速度与显示

| 配置 | 行为 |
|---|---|
| `mode="stepping"` | 游戏按调用推进；默认每步 1,000 ms，可设 `step_ms` |
| `step_ms` | 25–60,000 ms，必须为 25 ms 的整数倍；`reset()` 后从游戏时间 1,000 ms 开始 |
| `session.step(actions, ms=250)` | 为这一次调用指定毫秒数；多人共用一次推进 |
| `env.step(actions, seconds=0.25)` | 单 agent 包装层以秒为单位，并取整到 25 ms 粒度 |
| `mode="realtime"` | 游戏连续运行；`step()` 提交动作和读取观测，不保证两次观测间精确推进固定时长 |
| `debug("speed", factor=64)` | 设置虚拟时钟倍速；有效值大于 0 且不超过 2,048 |
| `render=False` | 抑制 Direct3D 9 的画面呈现；场景和 GPU 清理工作仍执行 |
| `window_mode="background"` | 默认后台窗口，不自动抢焦点；`background_visible=True` 可显示窗口 |
| `window_mode="interactive"` | 正常游戏窗口行为，失去焦点可能暂停；人工操作宜使用 realtime |
| `sound=False` | 单实例静音，也可通过 `WC3_SOUND=0` 设置默认值 |

1/64/256/2,048 倍时钟与 25 ms 步进已覆盖真机测试。倍速是时钟配置，不是实际吞吐承诺；CPU、图形设备、单位数量和并行实例数会影响墙钟耗时。

比赛结束或录像 EOF 可以提前结束一次步进。查看 `info["elapsed_ms"]` 和 `info["step_reason"]` 判断实际推进量。异常停滞或非预期短步进会令 session 进入故障状态，需要 `reset()` 重建进程。

## 7. 玩家、AI 与并行运行

`PlayerConfig` 支持 `human`、`orc`、`undead`、`night_elf`、`random`；控制者可选 `agent` 或 `computer`。配置 `setup=MatchSetup(...)` 后，种族、控制者、种子和出生点选项在开局前生效。未启用 setup 时，指定种族主要用于校验已加载的地图配置。

`MatchSetup(seed=42, randomize_starts=True)` 可固定随机种子并打乱地图已有出生点。重置和进程回收保留这组设置。只能使用地图定义的槽位和出生点，不能凭空增加玩家；当前真机验收包含 2、4、8 玩家地图。额外激活槽位的 `players[].team` 可能为 `-1`，应结合实际敌友关系判断。

`GameConfig.ai_difficulty` 为 `0` 简单、`1` 普通、`2` 疯狂，`None` 保留地图设置。`ai_agents=(0,)` 可让原生 melee AI 与 agent 同时控制指定 agent 槽位；`computer_agents=(0,)` 则保留电脑槽位的单位行为而不启动其 melee AI。二者都需要 `MatchSetup`。原生 AI 可能重新下令覆盖外部动作。

`GameSession` 的所有 agent 必须在每轮提供动作批次，即使没有动作也传空列表；一次合并提交后统一推进。电脑槽位无需提供动作批次。

`StepPool` 同时运行多个独立进程，支持统一配置或每局不同地图/玩家设置。池中游戏只支持 stepping，且配置的默认步长需要一致；相同模拟时间不意味着相同墙钟完成时间。实例失败时会保留结果位置并关闭失败进程，其他健康实例继续运行。池不会自动重开已结束的比赛。

## 8. 最小使用示例

以下 Python 示例在已安装包、配置游戏路径后运行。

### 单 agent 读取并移动农民

```python
from wc3env import Action, GameConfig, MatchSetup, PlayerConfig, WC3Env

config = GameConfig(
    map="(2)EchoIsles.w3x",
    players=(PlayerConfig(0, "human"), PlayerConfig(1, "orc", "computer")),
    setup=MatchSetup(seed=42),
    step_ms=250,
    render=False,
    sound=False,
)
with WC3Env(config) as env:
    obs = env.reset()
    worker = next(u for u in obs["units"] if u["type_id"] == "hpea")
    target_x = worker["x"] + (400 if worker["x"] < 0 else -400)
    action = Action(worker["unit_id"], "move", {"x": target_x, "y": worker["y"]})
    for tick in range(4):
        obs, done, info = env.step([action] if tick == 0 else [])
        print(obs["game_time_seconds"], info["elapsed_ms"], info["rejected"])
        if done:
            break
    current = next((u for u in obs["units"] if u["unit_id"] == worker["unit_id"]), None)
    if current:
        print("实际位置：", current["x"], current["y"], "当前命令：", current["order"])
```

### 同一局由两个 agent 控制

```python
from wc3env import GameConfig, GameSession, MatchSetup, PlayerConfig

config = GameConfig(
    map="(2)EchoIsles.w3x",
    players=(PlayerConfig(0, "human"), PlayerConfig(1, "orc")),
    setup=MatchSetup(seed=42),
    step_ms=250,
    render=False,
    sound=False,
)
with GameSession(config) as session:
    views = session.reset()
    session.debug("speed", factor=64)
    # 将两个空列表替换为各自策略根据 views[0]、views[1] 产生的动作。
    views, done, info = session.step({0: [], 1: []})
    print(views[0]["player"], views[1]["player"], info["elapsed_ms"])
```

### 并行运行两个游戏进程

```python
from wc3env import GameConfig, StepPool

pool = StepPool.launch(
    2,
    speed=64,
    config=GameConfig(map="(2)EchoIsles.w3x", step_ms=250, render=False, sound=False),
)
try:
    print(pool.run(steps=20).text())
finally:
    pool.close()
```

该示例只推进空动作对局并统计性能；接入策略时，应先通过各实例的 RPC 提交动作，再执行 `step_all()`。参数和失败处理见[对局与池配置](specs/configuration.md)。

## 9. 录像与生命周期

一局录制完成后调用 `env.save_replay(path)` 或 `session.save_replay(path)`，导出游戏原生 `.w3g`。保存会结束这一局的录制，每局只能保存一次；后续 `reset()` 才开始新的录制。

回放时，将 `GameConfig.map` 设置为 `.w3g` 路径，并使用原录制的 agent 槽位配置和 stepping 模式。原始地图必须可从本机安装中找到；回放不接受新动作、MatchSetup 或 AI 覆盖选项。读取到 EOF 后保留最后观测；若录像本身没有胜负结果，环境不会补造一个胜负。

录像有两个重要边界：`debug()` 的造兵、改资源等实验操作不写入录像；`drop_item` 的原生调用也不属于录制的命令。因此不能假定包含这些操作的实验会完整重现。使用普通原生订单的移动、建筑和战斗录像已通过独立回放比对。

普通地图 `reset()` 会在同一进程中重开，清理命令、观测、事件和分组，并保留已成功设置的速度、等待下限和呈现设置。默认每个进程最多运行 32 局，第 33 局前替换进程；可通过 `max_episodes_per_process` 调整。录像重置始终重建进程。

每个实例拥有独立 Runtime、地图副本、录像和日志目录，使用创建时保存的进程句柄关闭。源游戏安装目录保持原样，实例日志和运行目录会留存供排查。使用 `with` 或 `finally: close()` 释放进程。

## 10. 实验、诊断和数据资料

`debug()` 提供造兵、杀死/移除单位、修改资源/生命/魔法、设置英雄等级、给予物品、创建地面物品/可破坏物、调整联盟、暂停电脑 AI、无敌和读取执行订单等操作。这些属于实验控制，不受正常玩家经济流程约束；应与策略本身的普通动作区分。

`session.debug("overlay", panel="...")` 可显示本地游戏文字；`session.debug("ai_difficulty", player=1)` 可读取电脑难度。逐步调用的 `info["timings_ms"]` 和 `info["rpc_timings_ms"]` 提供主机、RPC、游戏线程等耗时，帮助区分策略耗时、传输耗时和模拟耗时。这些统计有重叠，不能全部相加当作总耗时。

`wc3agent` 随仓库保留了从本机 1.27a 提取的参考资料：836 单位、799 技能、273 物品、89 科技、237 buff，以及 Echo Isles 地图资料。保留稳定的英文名称并正确解码中文说明。资料是静态查询辅助，实时状态仍以游戏观测为准；自定义地图可能改写对象数据。提取工具位于 `tools/prepare/`，引擎诊断工具位于 `tools/port127/`。

## 11. 验证情况与适用边界

以下是 2026-09-27 移植验收结果；本次文档整理不代表重新执行整套真机测试。

本次另外校验了文档链接和 Python 语法，并在 1.27a 真机运行了本页三段完整示例：农民实际移动、双 agent 共享 250 ms 步进、两个独立实例各完成 20 次精确步进。结果保存在本地 `runs/features-127a-doc-check.log`。

| 验证范围 | 已记录结果 |
|---|---|
| 主机 / agent 单测 | 107 / 156 项通过 |
| 真机主测试 | 12 个模块与 4 个主场景通过 |
| 扩展测试 | 4 个模块；修复前置条件后的完整 16 个扩展场景通过 |
| AI 和显示 | 三种难度、AI agent 开局、D3D9 呈现切换、本地文字调用通过 |
| 完整离线比赛 | 原生 AI 完成比赛；重置和更换进程后，对所测地图/种子重复核对状态序列与结果 |
| 多地图 | Echo Isles、Secret Valley、Twisted Meadows、Twilight Ruins 的对应测试通过 |
| 稳定性与规模 | 64 轮重置；2,048 个额外飞行单位在呈现开/关条件下可观测、可控制 |
| 分发包 | 独立虚拟环境安装 wheel 后，真机移动、四次 250 ms 步进及同进程重置通过 |

当前结果只证明报告中指定的 Windows、D3D9、二进制和测试场景。其他补丁、Linux/Wine、其他图形后端、任意修改地图，以及任意硬件下的性能和长期稳定性尚未验证。多实例是多场独立离线游戏；LAN/Battle.net 联机不在当前接口范围内。

环境测试通过，也不代表某个外部 LLM 策略已经能稳定获胜。完整比赛的确定性证据适用于已测地图、配置和订单；不能推广为任意脚本、实时调度和外部策略下的确定性保证。

进一步阅读：[移植与验收](port-127a.md)、[兼容性证据](compatibility.md)、[实现设计](design.md)、[RPC 协议](specs/protocol.md)。
