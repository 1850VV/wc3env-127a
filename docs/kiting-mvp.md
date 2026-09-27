# 大法师风筝步兵 MVP

运行目录为本仓库。场景使用独立生成的平地 JASS 地图；1级大法师对1个原生步兵，无装备、无施法、不修改双方属性。步兵收到一次攻击目标命令后持续追击。

```powershell
.venv/Scripts/python -m tools.kiting_prepare
.venv/Scripts/python -m tools.kiting_mvp --mode kite --visible --realtime --out runs/kiting-mvp/watch
```

运行依赖已经适配的 wc3env 1.27a、本机 `.env` 游戏路径及支持的游戏二进制。地图构建和控制器仅用 Python 标准库与 wc3env。录像额外需要 `pillow mss numpy imageio[ffmpeg]`；录制会捕获游戏客户区，需保持游戏窗口不被其他窗口遮挡。

```powershell
.venv/Scripts/python -m tools.kiting_mvp --mode baseline --out runs/kiting-mvp/baseline
.venv/Scripts/python -m tools.kiting_mvp --mode kite --visible --record --ready-wait 15 --out runs/kiting-mvp/demo
.venv/Scripts/python -m tools.kiting_report
```

录制前等待15秒，供用户把游戏窗口置前。视频采样为每100 ms游戏时间一帧，10 fps播放，所以是游戏时间1倍速，不是墙钟性能证明。`--realtime` 尽量按游戏时间进行墙钟节拍，不能保证慢机器维持实时。

控制器通过己方可见单位、坐标和 `attacked` 事件保留攻击前摇，再后撤至下一次合适出手机会。`attacked` 是攻击启动事件，不证明命中；伤害验收采用后续HP下降及目标死亡。场景采用普通开阔地逃跑方向选择，边缘附近转向，未实现通用寻路。没有从敌方私有观测为控制策略提供信息；敌方观测只用于验收和视频面板。

## 验收

- 相同种子与初始血量下比较原地攻击和风筝。
- 大法师实际移动，循环攻击/后撤，击杀步兵并存活。
- 零接口拒绝；累计观测掉血低于原地攻击。
- `result.json`、`trace.json`、`summary.json` 与实机视频可相互核对。
- 地图中单位由debug spawn准备，此过程不进入原生录像。因此本MVP交付MP4和状态轨迹，不声称 `.w3g` 可复现这场战斗。

测试：仓库Python单测、agent单测、Ruff检查、native build回归，以及上述真实游戏对照。结果文件保存在 `runs/kiting-mvp/`，报告为 `report.html`。这里只验证固定微操场景，不表示通用微操、无伤风筝、多兵包围或实时墙钟性能已经通过。
