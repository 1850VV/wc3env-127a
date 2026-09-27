"""Actual Warcraft client capture with live surround telemetry."""

import ctypes
from ctypes import wintypes

from tools.kiting_video import Capture as BaseCapture


class Capture(BaseCapture):
    def frame(self, row):
        import numpy as np
        from PIL import Image, ImageDraw

        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        user32 = ctypes.windll.user32
        if not user32.GetClientRect(self.hwnd, ctypes.byref(rect)):
            raise RuntimeError("Game window disappeared")
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        shot = self.screen.grab({"left": origin.x, "top": origin.y, "width": rect.right, "height": rect.bottom})
        image = Image.new("RGB", (1536, 720), "#111925")
        game = Image.frombytes("RGB", shot.size, shot.rgb).resize((1152, 720))
        image.paste(game, (0, 0))
        draw = ImageDraw.Draw(image)
        target = row["target"]
        lines = [
            "十字包围 · 6 步兵",
            "Warcraft III 1.27a 实机",
            f"游戏时间  {row['t']:.2f} 秒",
            "",
            {"intercept": "分路超车 / 抢前方", "close": "前方截停 / 十字收口", "hold": "保持包围"}[row["phase"]],
            f"农民 HP  {target['hp']:.0f} / 220" if target else "农民已死亡",
            f"存活步兵  {len(row['army'])} / 6",
            f"受阻观测  {row['stable_seconds']:.2f} 秒",
            "农民仍在执行向右移动",
            "",
            "大法师留在后方，不参与堵路",
            "四方主位 + 两名侧翼补位",
            "原生移速与碰撞，未改属性",
            "",
            "每 50 ms 游戏时间决策",
            "画面按游戏时间 1× 播放",
        ]
        for n, line in enumerate(lines):
            draw.text(
                (1172, 24 + n * 39),
                line,
                font=self.font if n in (0, 4, 5) else self.small,
                fill="#80e0b0" if n in (4, 7) else "#e2e8f0",
            )
        self.writer.append_data(np.asarray(image))
        if self.frames in (0, 50, 100, 120):
            image.save(self.output / f"frame-{self.frames:04d}.png")
        self.frames += 1
