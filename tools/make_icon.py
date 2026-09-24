# -*- coding: utf-8 -*-
"""生成应用图标（一次性工具）：五子棋主题圆角图标。

输出 assets/icon.ico（多尺寸）与 assets/icon.png（256px，用于 README/GUI）。
用法：python tools/make_icon.py
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
os.makedirs(OUT, exist_ok=True)

S = 256  # 主画布尺寸


def rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def stone(draw, cx, cy, r, base, rim, highlight):
    """带高光的棋子。"""
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rim)
    draw.ellipse((cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2), fill=base)
    # 高光
    hr = int(r * 0.38)
    hx, hy = cx - int(r * 0.32), cy - int(r * 0.35)
    draw.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=highlight)


def make(size):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    scale = size / S
    if scale != 1:
        img = img.resize((size, size), Image.LANCZOS)
        d = ImageDraw.Draw(img)
    return img, d


# 1) 深色圆角底板
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((6, 6, S - 6, S - 6), radius=52, fill=(32, 36, 46, 255))
# 内描边
d.rounded_rectangle((6, 6, S - 6, S - 6), radius=52, outline=(70, 78, 96, 255), width=3)

# 2) 棋盘木色圆角面板
panel = (18, 18, 238, 238)
d.rounded_rectangle(panel, radius=26, fill=(232, 200, 143, 255))
d.rounded_rectangle(panel, radius=26, outline=(150, 116, 70, 255), width=5)

# 3) 网格线 5x5
gx0, gy0, gx1, gy1 = 52, 52, 204, 204
step = (gx1 - gx0) // 4
for i in range(5):
    x = gx0 + i * step
    d.line((x, gy0 - 8, x, gy1 + 8), fill=(156, 123, 83, 255), width=3)
    y = gy0 + i * step
    d.line((gx0 - 8, y, gx1 + 8, y), fill=(156, 123, 83, 255), width=3)

# 4) 棋子：白子 + 黑子 + 红色最新手标记（都在交叉点上）
stone(d, gx0 + step * 2, gy0 + step * 1, 22, (250, 250, 252), (150, 150, 155), (255, 255, 255))
stone(d, gx0 + step * 3, gy0 + step * 2, 22, (30, 30, 34), (0, 0, 0), (110, 110, 118))
d.ellipse((gx0 + step * 1 - 10, gy0 + step * 3 - 10,
           gx0 + step * 1 + 10, gy0 + step * 3 + 10), fill=(229, 72, 77, 255))

# 5) 保存
icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(os.path.join(OUT, "icon.ico"), sizes=icon_sizes)
img.save(os.path.join(OUT, "icon.png"))
print("saved assets/icon.ico, assets/icon.png")
