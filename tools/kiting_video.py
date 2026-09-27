"""Capture this experiment's game client and observed metrics at 10 frames/game-second."""

import ctypes
from ctypes import wintypes


class Capture:
    def __init__(self, game, output):
        import imageio.v2 as imageio
        import mss
        from PIL import ImageFont

        self.hwnd = game.windows()[0]
        self.output = output
        self.screen = mss.mss()
        self.writer = imageio.get_writer(output / "game.mp4", fps=10, codec="libx264", quality=8, macro_block_size=2)
        self.font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
        self.small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
        self.frames = 0
        self.closed = False

    def frame(self, row, mode):
        import numpy as np
        from PIL import Image, ImageDraw

        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        user32 = ctypes.windll.user32
        if not user32.GetClientRect(self.hwnd, ctypes.byref(rect)):
            raise RuntimeError("Game window disappeared during capture")
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        area = {"left": origin.x, "top": origin.y, "width": rect.right, "height": rect.bottom}
        shot = self.screen.grab(area)
        game_image = Image.frombytes("RGB", shot.size, shot.rgb).resize((1152, 720))
        image = Image.new("RGB", (1536, 720), "#111925")
        image.paste(game_image, (0, 0))
        draw = ImageDraw.Draw(image)
        title = "大法师风筝步兵" if mode == "kite" else "对照：原地攻击"
        lines = [
            title,
            "Warcraft III 1.27a 实机",
            f"游戏时间  {row['t']:.1f} 秒",
            "",
            f"大法师  {row['hero_hp']:.0f} / 450 HP",
            f"步兵  {row['enemy_hp']:.0f} / 420 HP",
            "",
            {
                "attack": "出手：保留攻击前摇",
                "retreat": "后撤：拉开攻击距离",
                "ready": "原地持续攻击",
                "finished": "战斗结束",
            }.get(row["phase"], row["phase"]),
            "",
            "1级 · 普攻 · 无装备",
            "双方原生属性，未修改数值",
            "步兵持续追击，无技能",
            "",
            "画面按游戏时间 1× 播放",
            "每 50 ms 游戏时间决策一次",
        ]
        y = 28
        for index, line in enumerate(lines):
            draw.text(
                (1172, y),
                line,
                font=self.font if index in (0, 4, 5) else self.small,
                fill="#7ed9af" if index == 4 else "#f4bb7e" if index == 5 else "#e2e8f0",
            )
            y += 39
        self.writer.append_data(np.asarray(image))
        if self.frames in (0, 150, 350):
            image.save(self.output / f"frame-{self.frames:04d}.png")
        self.frames += 1

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.writer.close()
            finally:
                self.screen.close()
