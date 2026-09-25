# -*- coding: utf-8 -*-
"""领域层：棋盘模型与纯逻辑（不依赖任何 I/O / UI）。"""
from .board import BoardGrid, coord_label, label_to_rc

__all__ = ["BoardGrid", "coord_label", "label_to_rc"]
