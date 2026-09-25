# -*- coding: utf-8 -*-
"""应用层服务契约（接口）。

依赖方向：application 只依赖 domain；infrastructure 实现这些接口；
组合根（app.py）负责装配。
"""
from __future__ import annotations

import abc

import numpy as np

from ..domain.board import BoardGrid


class Detection:
    """一次棋盘识别的结果。"""

    def __init__(self, board: np.ndarray, panel: tuple, points: np.ndarray,
                 spacing: float, unknown: list, overlay=None):
        self.board = board          # int8 (n, n)：0空 1黑 2白
        self.panel = panel          # (px, py, pw, ph) 截图内坐标
        self.points = points        # (n, n, 2) 每个交叉点 (x, y)
        self.spacing = spacing
        self.unknown = unknown      # [(label, hsv)]
        self.overlay = overlay      # 调试叠加图（可选）

    def stones(self):
        n = self.board.shape[0]
        return [(r, c, int(self.board[r, c]))
                for r in range(n) for c in range(n) if self.board[r, c]]


class BoardNotFoundError(Exception):
    """截屏中未找到/无法解析棋盘。"""


class IBoardDetector(abc.ABC):
    """棋盘识别器（infrastructure/vision 实现）。"""

    @abc.abstractmethod
    def detect(self, frame_bgr: np.ndarray, with_overlay: bool = False) -> Detection:
        ...


class IMoveEngine(abc.ABC):
    """对弈引擎（infrastructure/engine 实现：rapfi / simple）。"""

    name: str

    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def stop(self) -> None: ...

    @abc.abstractmethod
    def new_game(self) -> None: ...

    @abc.abstractmethod
    def best_move(self, grid, my_color: int, **kwargs):
        """返回 (r, c, info) 或 None。"""


class IWindowController(abc.ABC):
    """游戏窗口查找 / 截屏 / 前台化 / 鼠标（infrastructure/capture 实现）。"""

    @abc.abstractmethod
    def find_game_window(self) -> tuple[int, str, str]:
        """返回 (hwnd, title, process_name)。"""

    @abc.abstractmethod
    def capture_client(self, hwnd: int) -> tuple[np.ndarray, tuple[int, int]]:
        """返回 (BGR frame, 客户区屏幕原点)。"""

    @abc.abstractmethod
    def focus_window(self, hwnd: int) -> None: ...

    @abc.abstractmethod
    def is_foreground(self, hwnd: int) -> bool: ...

    @abc.abstractmethod
    def move_mouse(self, x: int, y: int) -> None: ...

    @abc.abstractmethod
    def click_at(self, x: int, y: int, hold: float = 0.06) -> None: ...

    @abc.abstractmethod
    def get_cursor_pos(self): ...

    @abc.abstractmethod
    def client_rect_screen(self, hwnd: int) -> tuple[int, int, int, int]: ...


class IEventSink(abc.ABC):
    """UI 事件出口（自动对弈服务经此推送日志/棋盘/状态给界面）。"""

    @abc.abstractmethod
    def publish(self, event: tuple) -> None:
        """event 形如 ("log", text) / ("board", detection) / ("active", bool)。"""
