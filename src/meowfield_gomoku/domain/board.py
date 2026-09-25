# -*- coding: utf-8 -*-
"""棋盘领域模型：坐标、棋盘状态与轮次判定（纯逻辑，可测试）。

约定：颜色 1=黑 2=白；行 0 基（对应棋盘行号 1-13），列 0 基（对应 A-M）。
"""
from __future__ import annotations

BOARD_N = 13

COLOR_BLACK = 1
COLOR_WHITE = 2


def coord_label(r: int, c: int) -> str:
    """(行, 列) 0 基 -> 游戏坐标，如 (6, 6) -> G7。"""
    return f"{chr(ord('A') + c)}{r + 1}"


def label_to_rc(label: str) -> tuple[int, int]:
    """游戏坐标（如 G7）-> (行, 列) 0 基。"""
    letter = "".join(ch for ch in label.upper() if ch.isalpha())
    digits = "".join(ch for ch in label if ch.isdigit())
    c = ord(letter) - ord("A")
    r = int(digits) - 1
    if not (0 <= r < BOARD_N and 0 <= c < BOARD_N):
        raise ValueError(f"坐标越界: {label}")
    return r, c


class BoardGrid:
    """13×13 棋盘状态的薄封装（底层 numpy int8 数组）。

    0=空 1=黑 2=白。提供轮次判定等纯领域逻辑，便于单元测试。
    """

    def __init__(self, grid=None, n: int = BOARD_N):
        import numpy as np

        self.n = n
        if grid is None:
            self._g = np.zeros((n, n), dtype=np.int8)
        else:
            self._g = np.asarray(grid, dtype=np.int8).reshape(n, n)

    # ---- 访问 ----
    @property
    def array(self):
        return self._g

    def at(self, r: int, c: int) -> int:
        return int(self._g[r, c])

    def stone_count(self) -> int:
        return int((self._g > 0).sum())

    def color_count(self, color: int) -> int:
        return int((self._g == color).sum())

    def is_empty(self) -> bool:
        return self.stone_count() == 0

    def copy(self) -> "BoardGrid":
        return BoardGrid(self._g.copy(), self.n)

    def __eq__(self, other):
        return isinstance(other, BoardGrid) and self.n == other.n \
            and (self._g == other._g).all()

    # ---- 领域规则 ----
    def mover_by_counts(self) -> int | None:
        """轮到哪方行棋：子少的一方。

        五子棋严格轮流，双方子数差必为 0 或 1；差 0 说明轮到先行方，
        但先行方是谁无法由当前局面推出 -> 返回 None。
        """
        b = self.color_count(COLOR_BLACK)
        w = self.color_count(COLOR_WHITE)
        if b == w:
            return None
        return COLOR_BLACK if b < w else COLOR_WHITE
