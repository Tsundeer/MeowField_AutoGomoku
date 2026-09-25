# -*- coding: utf-8 -*-
"""棋盘识别：定位棋盘面板 -> 拟合 13x13 交叉点 -> 分类落子。

算法概览（已用 samples/board_1080p.png 标定验证）：
1. 米色大面板：HSV 掩码最大连通域 -> 棋盘外框（分辨率无关，按比例工作）。
2. 网格线：面板内缩 ROI 中"线色"掩码按行/列投影，阈值分段取峰；
   因边缘线常被面板边框阴影遮暗，按等间距向两端外推补全到 13 条，
   外推位置需在面板内且全面板放宽掩码支撑度足够。
3. 落子分类：每个交叉点取中心小块的中位 HSV：
   V 低 -> 黑子；S 低 V 中 -> 白子；米色底 -> 空。
"""
import cv2
import numpy as np

from ... import config as C
from ...domain.board import coord_label


class BoardNotFound(Exception):
    pass


class Detection:
    def __init__(self, board, panel, points, spacing, unknown, overlay=None):
        self.board = board          # np.int8 (13,13)：0空 1黑 2白
        self.panel = panel          # (px, py, pw, ph) 截图内坐标
        self.points = points        # (13,13,2) 每个交叉点 (x, y)
        self.spacing = spacing
        self.unknown = unknown      # [(label, hsv)] 无法分类的点
        self.overlay = overlay      # 调试叠加图（可缓存）

    def stones(self):
        return [(r, c, int(self.board[r, c]))
                for r in range(self.board.shape[0])
                for c in range(self.board.shape[1]) if self.board[r, c]]


class BoardDetector:
    def __init__(self, **overrides):
        self.panel_h = overrides.get("panel_h", C.PANEL_H)
        self.panel_s = overrides.get("panel_s", C.PANEL_S)
        self.panel_v = overrides.get("panel_v", C.PANEL_V)
        self.line_b = overrides.get("line_b", C.LINE_B)
        self.line_b_relax = overrides.get("line_b_relax", C.LINE_B_RELAX)
        self.stone_dark_v = overrides.get("stone_dark_v", C.STONE_DARK_V)
        self.stone_white_s = overrides.get("stone_white_s", C.STONE_WHITE_S)
        self.stone_white_v = overrides.get("stone_white_v", C.STONE_WHITE_V)
        self.empty_s_min = overrides.get("empty_s_min", C.EMPTY_S_MIN)
        self.empty_v_min = overrides.get("empty_v_min", C.EMPTY_V_MIN)
        self.n = C.BOARD_N

    # ---------- 主入口 ----------
    def detect(self, frame_bgr, with_overlay=False):
        n = self.n
        px, py, pw, ph = self._find_panel(frame_bgr)
        inset = int(min(pw, ph) * 0.05)
        x0, y0 = px + inset, py + inset
        x1, y1 = px + pw - inset, py + ph - inset
        if x1 - x0 < n * 8 or y1 - y0 < n * 8:
            raise BoardNotFound("面板过小")

        roi_b = frame_bgr[y0:y1, x0:x1, 0].astype(np.int16)
        line_mask = (roi_b >= self.line_b[0]) & (roi_b <= self.line_b[1])
        col_proj = line_mask.sum(axis=0).astype(np.float64)
        row_proj = line_mask.sum(axis=1).astype(np.float64)
        if col_proj.max() < (y1 - y0) * 0.25 or row_proj.max() < (x1 - x0) * 0.25:
            raise BoardNotFound("未检测到网格结构")

        full_b = frame_bgr[py:py + ph, px:px + pw, 0].astype(np.int16)
        relax = (full_b >= self.line_b_relax[0]) & (full_b <= self.line_b_relax[1])

        xs = self._build_lines([c + x0 for c in self._runs(col_proj)], relax,
                               (px, pw), axis="v")
        ys = self._build_lines([c + y0 for c in self._runs(row_proj)], relax,
                               (py, ph), axis="h")
        sp = (xs[-1] - xs[0]) / (n - 1)
        spy = (ys[-1] - ys[0]) / (n - 1)
        if abs(sp - spy) > 0.18 * sp:
            raise BoardNotFound("横纵间距不一致")

        points = np.empty((n, n, 2))
        for i, y in enumerate(ys):
            for j, x in enumerate(xs):
                points[i, j] = (x, y)

        board = np.zeros((n, n), dtype=np.int8)
        unknown = []
        r = max(3, int(sp * 0.16))
        for i in range(n):
            for j in range(n):
                cx, cy = points[i, j]
                val, hsv = self._classify(frame_bgr, int(cx), int(cy), r)
                board[i, j] = val
                if val < 0:
                    unknown.append((coord_label(i, j), hsv))

        overlay = self._overlay(frame_bgr, xs, ys, board, points, sp) if with_overlay else None
        return Detection(board, (px, py, pw, ph), points, sp, unknown, overlay)

    # ---------- 面板定位 ----------
    def _find_panel(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv,
                           (self.panel_h[0], self.panel_s[0], self.panel_v[0]),
                           (self.panel_h[1], self.panel_s[1], self.panel_v[1]))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        if n <= 1:
            raise BoardNotFound("未找到棋盘面板")
        i = 1 + int(np.argmax(stats[1:, 4]))
        px, py, pw, ph = stats[i, 0], stats[i, 1], stats[i, 2], stats[i, 3]
        ar = pw / max(1, ph)
        if not (0.8 <= ar <= 1.25) or pw < 160:
            raise BoardNotFound(f"面板形状异常 w={pw} h={ph}")
        return px, py, pw, ph

    # ---------- 网格线 ----------
    @staticmethod
    def _runs(proj, ratio=0.5, merge_dist=None):
        th = proj.max() * ratio
        on = proj > th
        runs, start = [], None
        for i, v in enumerate(on):
            if v and start is None:
                start = i
            elif not v and start is not None:
                runs.append(((start + i - 1) / 2, i - start))
                start = None
        if start is not None:
            runs.append(((start + len(on) - 1) / 2, len(on) - start))
        if not runs:
            return []
        if merge_dist is None:
            merge_dist = max(6, int(len(proj) / 13 * 0.4))
        merged = [runs[0]]
        for c, w in runs[1:]:
            if c - merged[-1][0] < merge_dist:
                pc, pw_ = merged[-1]
                merged[-1] = ((pc * pw_ + c * w) / (pw_ + w), pw_ + w)
            else:
                merged.append((c, w))
        return [c for c, _ in merged]

    def _support(self, relax, pos, lo, size, axis):
        """放宽掩码下某线位置的支撑度（占可占长度的比例）。axis: 'v'=按列。"""
        if not (lo + size * 0.004 < pos < lo + size - size * 0.004):
            return -1.0
        half = max(3, int(size * 0.006))
        if axis == "v":
            a = max(0, int(pos - lo - half))
            b = min(size, int(pos - lo) + half + 1)
            if b <= a:
                return -1.0
            return float(relax[a:b, :].sum()) / relax.shape[1] / (b - a)
        a = max(0, int(pos - lo - half))
        b = min(size, int(pos - lo) + half + 1)
        if b <= a:
            return -1.0
        return float(relax[:, a:b].sum()) / relax.shape[0] / (b - a)

    def _build_lines(self, cs, relax, span, axis):
        lo, size = span
        if len(cs) < 3:
            raise BoardNotFound("网格线过少")
        lines = list(cs)
        sp = float(np.median(np.diff(lines)))
        n = self.n
        guard = size * 0.004
        while len(lines) < n:
            left, right = lines[0] - sp, lines[-1] + sp
            sl = self._support(relax, left, lo, size, axis)
            sr = self._support(relax, right, lo, size, axis)
            if sl < 0.10 and sr < 0.10:
                raise BoardNotFound(f"无法外推补线（当前{len(lines)}条）")
            if sl >= sr:
                lines.insert(0, left)
            else:
                lines.append(right)
        if len(lines) > n:
            lines = lines[:n]
        d = np.diff(lines)
        if float(np.abs(d - sp).max()) > sp * 0.12:
            raise BoardNotFound("网格间距不均匀")
        return lines

    # ---------- 落子分类 ----------
    def _classify(self, frame, cx, cy, r):
        h, w = frame.shape[:2]
        patch = frame[max(0, cy - r):min(h, cy + r) + 1,
                      max(0, cx - r):min(w, cx + r) + 1]
        if patch.size == 0:
            return -1, None
        med = np.median(patch.reshape(-1, 3), axis=0)
        hsv = cv2.cvtColor(np.uint8([[med]]), cv2.COLOR_BGR2HSV)[0, 0]
        H, S, V = int(hsv[0]), int(hsv[1]), int(hsv[2])
        if V < self.stone_dark_v:
            return 1, (H, S, V)
        if S <= self.stone_white_s and self.stone_white_v[0] <= V <= self.stone_white_v[1]:
            return 2, (H, S, V)
        if S >= self.empty_s_min and V >= self.empty_v_min:
            return 0, (H, S, V)
        return -1, (H, S, V)

    # ---------- 调试图 ----------
    def _overlay(self, frame, xs, ys, board, points, sp):
        dbg = frame.copy()
        px, py, pw, ph = None, None, None, None
        for i in range(board.shape[0]):
            for j in range(board.shape[1]):
                x, y = int(points[i, j][0]), int(points[i, j][1])
                v = board[i, j]
                if v == 1:
                    cv2.circle(dbg, (x, y), int(sp * 0.32), (0, 0, 200), 2)
                elif v == 2:
                    cv2.circle(dbg, (x, y), int(sp * 0.32), (255, 0, 0), 2)
                else:
                    cv2.circle(dbg, (x, y), 2, (0, 0, 255), -1)
                cv2.putText(dbg, coord_label(i, j), (x + 6, y - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, max(0.3, sp / 160),
                            (60, 60, 60), 1, cv2.LINE_AA)
        return dbg
