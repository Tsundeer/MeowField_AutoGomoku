# -*- coding: utf-8 -*-
"""自动对弈状态机离线逻辑测试（不打开窗口、不点击）。

用法：python tools/test_logic.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

import auto_player  # noqa: E402

N = 13
fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


def make_player(color="auto"):
    p = auto_player.AutoPlayer(our_color=color, engine_kind="simple",
                               move_delay=0.0)
    p.active = True
    p._verify_no_ghost = lambda r, c: True
    clicked = []

    class FakeAI:
        def start(self): pass
        def stop(self): pass
        def new_game(self): pass

        def best_move(self, grid, my_color, **kw):
            best = None
            for r in range(13):
                for c in range(13):
                    if int(grid[r][c]) == 0:
                        d = abs(r - 6) + abs(c - 6)
                        if best is None or d < best[0]:
                            best = (d, r, c)
            return best[1], best[2], {"engine": "fake"}

    p._ensure_ai = lambda: FakeAI()

    def fake_click(r, c):
        clicked.append((r, c))
        return True

    p._click_cell = fake_click
    return p, clicked


def feed(p, board):
    """稳定地喂入新局面（绕过截屏轮询），并模拟轮询线程的思考收尾。"""
    p.same_count = 99
    p._process_change(board.copy())
    if p.thinking:
        if p._think_done.wait(timeout=30):
            p._finish_think()


def g(stones):
    b = np.zeros((N, N), dtype=np.int8)
    for r, c, v in stones:
        b[r, c] = v
    return b


# 1) 中盘接管：指定颜色 + 子数判轮次（黑2白1 -> 轮白 -> 我方白 -> 应出招）
p, clicked = make_player("2")
p.confirmed = None
feed(p, g([(7, 7, 1), (7, 8, 1), (6, 6, 2)]))
check("中盘接管-子数判轮次", len(clicked) == 1, f"clicked={clicked}")
check("接管颜色为白", p.our_color == 2)

# 2) 自动学习：初始1黑(已采纳)，观测白子落下(子数表明白该走，判为对方) -> 以黑接管
p, clicked = make_player("auto")
p.confirmed = None
feed(p, g([(7, 7, 1)]))            # 初始 1 黑子
p.same_count = 99
p.confirmed = g([(7, 7, 1)])       # 手动锁定为已确认局面
feed(p, g([(7, 7, 1), (6, 6, 2)]))  # 白子落下 -> 学习: 我=黑(暂定)
check("自动学习-暂定黑色", p.our_color == 1 and p.learning_move)
check("自动学习-已出招", len(clicked) == 1)
r, c = clicked[0]
# 点击生效：棋盘上 (r,c) 出现黑子（铁证）
feed(p, g([(7, 7, 1), (6, 6, 2), (r, c, 1)]))
check("自动学习-点击锁定黑色", p.our_color == 1 and p.color_locked)
check("自动学习-轮到对方(白)", p.expected_next == 2)

# 3) 自动学习纠正：观测白子 -> 以黑接管 -> 点击未生效 -> 纠正为白、等黑
p, clicked = make_player("auto")
p.confirmed = None
feed(p, g([(7, 7, 1)]))
p.same_count = 99
p.confirmed = g([(7, 7, 1)])
feed(p, g([(7, 7, 1), (6, 6, 2)]))   # 观测到白子 -> 暂定我=黑
check("纠正前-暂定黑色", p.our_color == 1)
check("纠正前-已试探出招", len(clicked) == 1)
# 点击未生效（局面没变化），等待超时
p.await_deadline = time.time() - 1
p._check_click_timeout()
check("纠正-颜色改为白色", p.our_color == 2)
check("纠正-等待黑方(对方)", p.expected_next == 1)
check("纠正-不再重试", p.awaiting is None)

# 4) 子数相等且历史未知：不盲目出招
p, clicked = make_player("1")
p.confirmed = None
feed(p, g([(7, 7, 1), (6, 6, 2)]))
check("黑白相等-不冒进", len(clicked) == 0)

# 5) 我方手动落子被识别并继续接管：我=黑，黑手动落子 -> 等白 -> 白落 -> 我出招
p, clicked = make_player("1")
p.confirmed = None
feed(p, g([(7, 7, 1)]))                       # 1黑 -> 轮白
feed(p, g([(7, 7, 1), (6, 6, 2)]))            # 白落 -> 轮黑(我)
check("已知颜色-轮到我方出招", len(clicked) == 1)
# 黑没下（假设引擎那步没算），用户手动在别处下了黑子
p.awaiting = None
r0, c0 = 8, 8
p.same_count = 99
p.confirmed = g([(7, 7, 1), (6, 6, 2)])
feed(p, g([(7, 7, 1), (6, 6, 2), (r0, c0, 1)]))
check("手动黑子-识别为我方", p.expected_next == 2)
# 白应招 -> 轮到我 -> 出招
clicked.clear()
feed(p, g([(7, 7, 1), (6, 6, 2), (r0, c0, 1), (5, 5, 2)]))
check("白应招后-自动续下", len(clicked) == 1)

# 6) 停摆根因回归：我方确认 + 对方快招出现在同一批差分里
p, clicked = make_player("1")
p.confirmed = None
feed(p, g([(7, 7, 1)]))
feed(p, g([(7, 7, 1), (6, 6, 2)]))     # 白落 -> 轮黑 -> 出招
r, c = clicked[0]
p.awaiting = (r, c)
p.await_deadline = time.time() + 30
p.same_count = 99
p.confirmed = g([(7, 7, 1), (6, 6, 2)])
# 下一轮同时看到: 我方棋子确认 + 对方快速应招
feed(p, g([(7, 7, 1), (6, 6, 2), (r, c, 1), (0, 0, 2)]))
check("同批差分-确认无误", p.our_color == 1 and p.color_locked)
check("同批差分-轮次仍是我方", p.expected_next == 1)
check("同批差分-继续出招不停摆", len(clicked) == 2)

# 7) 开启自动时已轮到我方 -> 立即出手接管
p, clicked = make_player("1")
p.confirmed = None
p.active = False
feed(p, g([(6, 6, 2), (6, 7, 2), (7, 7, 1)]))   # 锁定: 黑1白2 -> 轮黑(我)
check("开启前不出手", len(clicked) == 0)
p.set_params(active=True)
if p.thinking:
    p._think_done.wait(timeout=30)
    if p._think_done.is_set():
        p._finish_think()
check("开启即接管", len(clicked) == 1)

# 8) 先手开局：空盘 + 指定黑色 + 开启 -> 自动下中心 H7
p, clicked = make_player("1")
p.confirmed = None
p.active = False
feed(p, g([]))                       # 空盘锁定
check("空盘开启前不出手", len(clicked) == 0)
p.set_params(active=True)
check("先手开局-下中心H7", clicked == [(6, 6)])
check("先手开局-待确认", p.awaiting == (6, 6))
p.same_count = 99
p.confirmed = g([])
feed(p, g([(6, 6, 1)]))              # 中心出现黑子 -> 确认
check("先手开局-颜色锁定黑色", p.our_color == 1 and p.color_locked)
check("先手开局-轮到对方", p.expected_next == 2)

# 9) 自动模式 + 空盘：先试探中心；若没轮到我方则回退等待
p, clicked = make_player("auto")
p.confirmed = None
p.active = False
feed(p, g([]))
p.set_params(active=True)
check("自动空盘-先试探中心", clicked == [(6, 6)])
p.await_deadline = time.time() - 1
p._check_click_timeout()
check("自动空盘-试探失败转等待", p.awaiting is None and p.our_color is None)
# 对方随后落黑子 -> 学习接管
p.same_count = 99
p.confirmed = g([])
feed(p, g([(7, 7, 1)]))
check("对方先落子-接管出招", len(clicked) == 2)

print()
if fails:
    print(f"共 {len(fails)} 项失败: {fails}")
    sys.exit(1)
print("全部通过 ✔")
