# -*- coding: utf-8 -*-
"""五子棋引擎：增量窗口计分 + α-β 迭代加深。

棋盘用一维 list（含哨兵边框），所有线（行/列/对角线）预计算成索引元组；
落子/撤销只重算穿过该点的 4 条线的分值，评估 O(1)。
搜索带强制规则：能连五直接下；对方能连五必须堵。
"""
import time

FIVE = 10_000_000
WIN_SCORE = FIVE * 10

# 一个5格窗口内，某色纯色 k 子（对手为0）的分值
W = (0, 4, 32, 512, 8192, FIVE)

DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))


def coord_label(r, c):
    return f"{chr(ord('A') + c)}{r + 1}"


class GomokuEngine:
    def __init__(self, size=13):
        self.N = size
        self.P = size + 4  # 两侧各2格哨兵
        self._precompute_lines()
        self.reset()

    # ---------- 结构 ----------
    def _idx(self, r, c):
        return (r + 2) * self.P + (c + 2)

    def _precompute_lines(self):
        n, P = self.N, self.P
        flat = lambda r, c: (r + 2) * P + (c + 2)
        lines = []
        cell_lines = [[] for _ in range(P * P)]
        for r in range(n):
            lines.append([flat(r, c) for c in range(n)])
        for c in range(n):
            lines.append([flat(r, c) for r in range(n)])
        for s in range(-(n - 1), n):  # 主对角 r-c=s
            cells = [flat(r, r - s) for r in range(n) if 0 <= r - s < n]
            if len(cells) >= 5:
                lines.append(cells)
        for s in range(0, 2 * n - 1):  # 副对角 r+c=s
            cells = [flat(r, s - r) for r in range(n) if 0 <= s - r < n]
            if len(cells) >= 5:
                lines.append(cells)
        for li, line in enumerate(lines):
            for pos in line:
                cell_lines[pos].append(li)
        self.lines = [tuple(l) for l in lines]
        self.cell_lines = [tuple(x) for x in cell_lines]
        # 每格相邻（切比雪夫距离<=2）偏移
        nb = []
        for dr in (-2, -1, 0, 1, 2):
            for dc in (-2, -1, 0, 1, 2):
                if dr or dc:
                    nb.append(dr * P + dc)
        self.nb_offsets = tuple(nb)

    def reset(self):
        P = self.P
        self.b = [0] * (P * P)
        for i in range(P * P):
            r, c = divmod(i, P)
            if r < 2 or r >= P - 2 or c < 2 or c >= P - 2:
                self.b[i] = 3
        self.line_scores = [[0, 0]] * len(self.lines)
        self.total = [0, 0]          # [黑分, 白分]
        self.stones = 0
        self.nbcount = [0] * (P * P)

    def set_board(self, grid):
        """grid: 13x13，0空1黑2白。"""
        self.reset()
        for r in range(self.N):
            for c in range(self.N):
                v = int(grid[r][c])
                if v:
                    self.place(self._idx(r, c), v)

    # ---------- 增量计分 ----------
    def _line_score(self, line):
        b = self.b
        s1 = s2 = 0
        for i in range(len(line) - 4):
            c1 = c2 = 0
            for p in line[i:i + 5]:
                v = b[p]
                if v == 1:
                    c1 += 1
                elif v == 2:
                    c2 += 1
            if c1:
                if not c2:
                    s1 += W[c1]
            elif c2:
                s2 += W[c2]
        return s1, s2

    def place(self, pos, color):
        self.b[pos] = color
        self.stones += 1
        for off in self.nb_offsets:
            self.nbcount[pos + off] += 1
        for li in self.cell_lines[pos]:
            old = self.line_scores[li]
            self.total[0] -= old[0]
            self.total[1] -= old[1]
            new = self._line_score(self.lines[li])
            self.line_scores[li] = new
            self.total[0] += new[0]
            self.total[1] += new[1]

    def unplace(self, pos):
        color = self.b[pos]
        self.b[pos] = 0
        self.stones -= 1
        for off in self.nb_offsets:
            self.nbcount[pos + off] -= 1
        for li in self.cell_lines[pos]:
            old = self.line_scores[li]
            self.total[0] -= old[0]
            self.total[1] -= old[1]
            new = self._line_score(self.lines[li])
            self.line_scores[li] = new
            self.total[0] += new[0]
            self.total[1] += new[1]
        return color

    # ---------- 战术检查 ----------
    def _makes_five(self, pos, color):
        P = self.P
        b = self.b
        b[pos] = color
        ok = False
        for dr, dc in DIRS:
            cnt = 1
            r, c = divmod(pos, P)
            r -= 2
            c -= 2
            rr, cc = r + dr, c + dc
            while 0 <= rr < self.N and 0 <= cc < self.N and b[(rr + 2) * P + cc + 2] == color:
                cnt += 1
                rr += dr
                cc += dc
            rr, cc = r - dr, c - dc
            while 0 <= rr < self.N and 0 <= cc < self.N and b[(rr + 2) * P + cc + 2] == color:
                cnt += 1
                rr -= dr
                cc -= dc
            if cnt >= 5:
                ok = True
                break
        b[pos] = 0
        return ok

    # ---------- 候选生成 ----------
    def _candidates(self, color, cap):
        b, nb = self.b, self.nbcount
        P = self.P
        cands = []
        for pos in range(2 * P + 2, (self.N + 2) * P + 2):
            if b[pos] == 0 and nb[pos] > 0:
                r, c = divmod(pos, P)
                cands.append((nb[pos] * 16 - (abs(r - P // 2) + abs(c - P // 2)), pos))
        if not cands and self.stones == 0:
            return [self._idx(self.N // 2, self.N // 2)]
        cands.sort(reverse=True)
        return [p for _, p in cands[:cap]]

    # ---------- 搜索 ----------
    def _eval(self, color):
        opp = 3 - color
        return self.total[color - 1] - self.total[opp - 1]

    def _search(self, color, depth, alpha, beta, ply):
        opp = 3 - color
        # 我方能连五 -> 直接赢
        for pos in self._candidates(color, 20):
            if self._makes_five(pos, color):
                return WIN_SCORE - ply, pos
        # 对方能连五 -> 只有堵点可选
        threat_cells = [pos for pos in self._candidates(opp, 20)
                        if self._makes_five(pos, opp)]
        if threat_cells:
            moves = threat_cells
        else:
            if depth <= 0:
                return self._eval(color), None
            moves = self._candidates(color, self.branch)
        if not moves:
            return 0, None

        best = -10 ** 18
        best_pos = None
        for pos in moves:
            self.place(pos, color)
            if threat_cells and any(self._makes_five(t, opp)
                                    for t in threat_cells if t != pos):
                # 堵了一个点对方还有连五点 -> 仍输
                score = -(WIN_SCORE - ply - 1)
            else:
                sc, _ = self._search(opp, depth - 1, -beta, -alpha, ply + 1)
                score = -sc
            self.unplace(pos)
            if score > best:
                best = score
                best_pos = pos
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break
        return best, best_pos

    def best_move(self, grid, color, time_limit=1.0, max_depth=8, branch=14):
        """grid: 13x13。返回 (r, c, info) 或 None。"""
        self.set_board(grid)
        if self.stones == 0:
            m = self.N // 2
            return m, m, {"note": "开局天元"}
        self.branch = max(6, int(branch))
        deadline = time.time() + time_limit
        if self.stones >= self.N * self.N:
            return None
        best_pos, best_depth = None, 0
        nodes = [0]
        for depth in range(2, max_depth + 1, 2):
            # 迭代加深：用上一轮最佳着法优先
            self.pv_move = best_pos
            t0 = time.time()
            try:
                score, pos = self._search_root(color, depth, deadline, nodes)
            except _Timeout:
                break
            if pos is not None:
                best_pos, best_depth = pos, depth
                if score >= WIN_SCORE - 100 or score <= -(WIN_SCORE - 100):
                    break  # 已找到必胜/必败，浅层即可
            if time.time() - t0 > time_limit * 0.6:
                break
        if best_pos is None:
            return None
        r, c = divmod(best_pos, self.P)
        return r - 2, c - 2, {"depth": best_depth, "nodes": nodes[0]}

    def _search_root(self, color, depth, deadline, nodes):
        opp = 3 - color
        for pos in self._candidates(color, 24):
            if self._makes_five(pos, color):
                return WIN_SCORE, pos
        threat_cells = [pos for pos in self._candidates(opp, 24)
                        if self._makes_five(pos, opp)]
        moves = threat_cells or self._candidates(color, self.branch * 2)
        if self.pv_move is not None and self.pv_move in moves:
            moves.remove(self.pv_move)
            moves.insert(0, self.pv_move)
        best, best_pos = -10 ** 18, None
        alpha, beta = -10 ** 18, 10 ** 18
        for pos in moves:
            if time.time() > deadline:
                raise _Timeout()
            nodes[0] += 1
            self.place(pos, color)
            if threat_cells and any(self._makes_five(t, opp)
                                    for t in threat_cells if t != pos):
                score = -(WIN_SCORE - 1)
            else:
                sc, _ = self._search(opp, depth - 1, -beta, -alpha, 1)
                score = -sc
            self.unplace(pos)
            if score > best:
                best, best_pos = score, pos
                if score > alpha:
                    alpha = score
        return best, best_pos


class _Timeout(Exception):
    pass
