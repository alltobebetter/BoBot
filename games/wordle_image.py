"""Wordle 图片生成（Pillow + Gyazo 上传）。

用彩色方块绘制 Wordle 棋盘，比纯 emoji 更直观美观。
Pillow 未安装时自动降级为 None，命令层回退到 emoji 文本。
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from utils.logger import log


class WordleImageGenerator:
    """Wordle 结果图片生成器。"""

    # 颜色定义（RGB）
    COLORS = {
        "correct": (106, 170, 100),    # 绿色 — 位置正确
        "present": (201, 180, 88),     # 黄色 — 存在但位置错
        "absent": (120, 124, 126),     # 灰色 — 不存在
        "empty": (211, 214, 218),      # 空白格
        "background": (255, 255, 255), # 背景
        "text": (255, 255, 255),       # 字母白色
        "border": (211, 214, 218),     # 边框
    }

    # 尺寸
    CELL_SIZE = 62
    CELL_GAP = 5
    PADDING = 20

    def __init__(self, font_path: str = None):
        self.font_path = font_path
        self._font: Optional[ImageFont.FreeTypeFont] = None
        self._font_small: Optional[ImageFont.FreeTypeFont] = None
        if PIL_AVAILABLE:
            self._load_font()

    def _load_font(self) -> None:
        font_size = 36
        font_size_small = 14

        # 优先自定义字体
        if self.font_path and Path(self.font_path).exists():
            try:
                self._font = ImageFont.truetype(self.font_path, font_size)
                self._font_small = ImageFont.truetype(self.font_path, font_size_small)
                return
            except Exception as e:
                log.warning("加载自定义字体失败", error=str(e))

        # 尝试系统字体
        system_fonts = [
            "arial.ttf",
            "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for name in system_fonts:
            try:
                self._font = ImageFont.truetype(name, font_size)
                self._font_small = ImageFont.truetype(name, font_size_small)
                return
            except Exception:
                continue

        # 兜底默认字体
        self._font = ImageFont.load_default()
        self._font_small = ImageFont.load_default()

    def generate(
        self,
        guesses: List[dict],
        max_guesses: int = 6,
        show_answer: bool = False,
        answer: str = "",
    ) -> Optional[bytes]:
        """生成 Wordle 棋盘 PNG 图片。

        Args:
            guesses: [{"word": "APPLE", "result": ["correct","present",...]}]
            max_guesses: 最大行数
            show_answer: 是否在底部显示答案
            answer: 答案单词

        Returns:
            PNG 字节数据，Pillow 不可用时返回 None
        """
        if not PIL_AVAILABLE:
            return None

        try:
            word_length = len(guesses[0]["word"]) if guesses else 5
            width = self.PADDING * 2 + word_length * (self.CELL_SIZE + self.CELL_GAP) - self.CELL_GAP
            height = self.PADDING * 2 + max_guesses * (self.CELL_SIZE + self.CELL_GAP) - self.CELL_GAP
            if show_answer and answer:
                height += 30

            img = Image.new("RGB", (width, height), self.COLORS["background"])
            draw = ImageDraw.Draw(img)

            for row in range(max_guesses):
                for col in range(word_length):
                    x = self.PADDING + col * (self.CELL_SIZE + self.CELL_GAP)
                    y = self.PADDING + row * (self.CELL_SIZE + self.CELL_GAP)

                    if row < len(guesses):
                        guess = guesses[row]
                        letter = guess["word"][col]
                        status = guess["result"][col]
                        color = self.COLORS.get(status, self.COLORS["empty"])
                    else:
                        letter = ""
                        color = self.COLORS["empty"]

                    draw.rectangle(
                        [x, y, x + self.CELL_SIZE, y + self.CELL_SIZE],
                        fill=color,
                        outline=self.COLORS["border"],
                        width=2,
                    )

                    if letter:
                        bbox = draw.textbbox((0, 0), letter, font=self._font)
                        lw = bbox[2] - bbox[0]
                        lh = bbox[3] - bbox[1]
                        lx = x + (self.CELL_SIZE - lw) // 2
                        ly = y + (self.CELL_SIZE - lh) // 2 - 5
                        draw.text((lx, ly), letter, fill=self.COLORS["text"], font=self._font)

            if show_answer and answer:
                text = f"Answer: {answer}"
                bbox = draw.textbbox((0, 0), text, font=self._font_small)
                ax = (width - (bbox[2] - bbox[0])) // 2
                draw.text((ax, height - 25), text, fill=(100, 100, 100), font=self._font_small)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            log.error("生成 Wordle 图片失败", exc=e)
            return None


# 全局实例 —— 使用自带等宽字体
_font_path = str(Path(__file__).resolve().parent.parent / "data" / "fonts" / "c16xcnr.ttf")
_generator = WordleImageGenerator(font_path=_font_path)


def generate_wordle_image(
    guesses: List[dict], max_guesses: int = 6, show_answer: bool = False, answer: str = ""
) -> Optional[bytes]:
    """便捷函数：生成 Wordle 棋盘图片。"""
    return _generator.generate(guesses, max_guesses, show_answer, answer)
