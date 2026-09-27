"""Evaluate saved real-game observations and make a local video report."""

import json
from pathlib import Path


def load(folder):
    result = json.loads((folder / "result.json").read_text())
    trace = json.loads((folder / "trace.json").read_text())
    result["observed_damage_taken"] = sum(max(0, a["hero_hp"] - b["hero_hp"]) for a, b in zip(trace, trace[1:]))
    result["moving_samples"] = sum(
        1
        for a, b in zip(trace, trace[1:])
        if a["hero"] and b["hero"] and abs(a["hero"]["x"] - b["hero"]["x"]) + abs(a["hero"]["y"] - b["hero"]["y"]) > 1
    )
    return result


def main():
    root = Path("runs/kiting-mvp")
    baseline, kite = load(root / "baseline"), load(root / "demo")
    checks = {
        "same_seed_and_starting_health": baseline["seed"] == kite["seed"]
        and baseline["initial"]["hero_hp"] == kite["initial"]["hero_hp"] == 450
        and baseline["initial"]["enemy_hp"] == kite["initial"]["enemy_hp"] == 420,
        "footman_dead_and_archmage_alive": kite["won"],
        "observed_movement": kite["moving_samples"] > 100,
        "both_attack_and_retreat": kite["orders"]["attack"] >= 5 and kite["orders"]["move"] >= 5,
        "zero_rejected_actions": not baseline["rejected"] and not kite["rejected"],
        "less_observed_damage_than_standing": kite["observed_damage_taken"] < baseline["observed_damage_taken"],
        "video_exists": (root / "demo/game.mp4").stat().st_size > 10000,
    }
    reduction = 100 * (1 - kite["observed_damage_taken"] / baseline["observed_damage_taken"])
    video = "demo/game-reviewed.mp4" if (root / "demo/game-reviewed.mp4").exists() else "demo/game.mp4"
    video_note = ""
    if (root / "occlusion.json").exists():
        occlusion = json.loads((root / "occlusion.json").read_text())
        seconds = sum(b - a + 1 for a, b in occlusion["ranges"]) / occlusion["fps"]
        video_note = f"<p>录制期间有{seconds:.1f}秒游戏画面被其他窗口遮挡；审阅版以明确提示替换这些画面，保留右侧真实状态，不生成或伪造游戏画面。24秒短预览不含遮挡。</p>"
    summary = {
        "acceptance": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "baseline": baseline,
        "kite": kite,
        "observed_damage_reduction_percent": reduction,
    }
    if (root / "seed43/result.json").exists():
        summary["second_seed"] = load(root / "seed43")
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(
        f"<tr><td>{label}</td><td>{r['hero_hp']:.0f}/450</td><td>{r['observed_damage_taken']:.0f}</td><td>{r['elapsed_game_seconds']:.2f} 秒</td><td>{'击杀' if r['won'] else '未击杀'}</td></tr>"
        for label, r in (("原地攻击", baseline), ("风筝控制", kite))
    )
    html = f"""<!doctype html><html lang="zh"><meta charset="utf-8"><title>大法师风筝步兵 · 实机 MVP</title>
<style>body{{margin:0;background:#0c1320;color:#e4edf7;font:17px/1.65 system-ui}}main{{max-width:1180px;margin:32px auto;padding:0 24px}}h1{{font-size:32px;margin-bottom:6px}}p{{color:#acbdd1}}video{{width:100%;border-radius:12px;background:black}}table{{width:100%;border-collapse:collapse;margin:24px 0}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #2b3b50}}.metric{{color:#8de0b5;font-size:24px}}a{{color:#91c7ff}}</style>
<main><h1>大法师风筝步兵</h1><p>Warcraft III 1.27a · 真实游戏画面 · 外部 Python 控制 · 固定场景 MVP</p>
<video controls autoplay muted playsinline preload="metadata" poster="demo/frame-0150.png" src="{video}"></video>
<p>红方：1级大法师；蓝方：1个步兵持续追击。双方原生属性，无装备、无技能。视频每秒对应1秒游戏时间。</p>
<div class="metric">累计观测掉血减少 {reduction:.1f}% · 最终 {kite["hero_hp"]:.0f}/450 HP · {summary["acceptance"]}</div>
<table><tr><th>控制方式</th><th>大法师剩余血量</th><th>累计观测掉血</th><th>击杀游戏时间</th><th>结果</th></tr>{rows}</table>
<p>累计观测掉血为相邻采样中的血量下降之和，回血单独排除；它不是直接伤害事件总和。风筝更保血，但本版击杀更慢。只验证开放平地、单个步兵，尚不涵盖障碍、多单位包围或联网对战。</p>
<p>控制器每50 ms游戏时间读取己方视野内状态；保留攻击前摇，再后撤拉开距离。接受命令不算成功，验收依据为实际坐标变化、血量下降和目标死亡。比赛准备通过spawn创建单位，未把这种准备过程当作可回放的原生录像。</p>
{video_note}
<p><a href="preview.mp4">24秒动作预览</a> · <a href="summary.json">验收数据</a> · <a href="demo/trace.json">逐帧状态与动作</a> · <a href="{video}">完整视频（遮挡已标注）</a></p></main></html>"""
    (root / "report.html").write_text(html, encoding="utf-8")
    print(json.dumps({"acceptance": summary["acceptance"], "checks": checks, "damage_reduction_percent": reduction}))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
