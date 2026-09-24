# -*- coding: utf-8 -*-
"""Rapfi 引擎协议连通测试（不依赖游戏）。

用法：python tools/test_rapfi.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from gomoku_ai import RapfiAI, find_rapfi_exes  # noqa: E402

N = 13
logs = []


def log(s):
    logs.append(s)
    print(s)


def main():
    exes = find_rapfi_exes()
    print("候选引擎:", [os.path.basename(p) for p in exes])
    assert exes, "engines/ 下没有 rapfi"

    ai = RapfiAI(size=N, log_fn=log)
    ai.start()

    # 1) 空盘 -> 天元附近
    g = np.zeros((N, N), dtype=np.int8)
    t0 = time.time()
    r, c, info = ai.best_move(g, 1, time_limit=1.0)
    print(f"空盘首着: {chr(65+c)}{r+1}  ({time.time()-t0:.2f}s)  info={info}")
    assert (r, c) == (6, 6)

    # 2) 我方执白：对方(黑)H8=G? 摆一个黑棋 H8 -> 我方白应招
    g2 = np.zeros((N, N), dtype=np.int8)
    g2[7, 7] = 1  # 黑 H8
    t0 = time.time()
    r2, c2, _ = ai.best_move(g2, 2, time_limit=1.0)
    print(f"我方执白应招: {chr(65+c2)}{r2+1}  ({time.time()-t0:.2f}s)")
    assert g2[r2, c2] == 0 and 0 <= r2 < N and 0 <= c2 < N

    # 3) 对方活三必堵场景（我方执黑）
    g3 = np.zeros((N, N), dtype=np.int8)
    g3[6, 5] = 2; g3[6, 6] = 2; g3[6, 7] = 2   # 白活三 F7 G7 H7
    g3[3, 3] = 1; g3[4, 4] = 1                 # 我方黑两子
    r3, c3, _ = ai.best_move(g3, 1, time_limit=1.5)
    label = f"{chr(65+c3)}{r3+1}"
    print(f"活三应对: {label}")
    assert label in ("E7", "I7", "E8", "I8", "E6", "I6",
                     "F8", "H8", "F6", "H6"), f"未处理白方活三: {label}"

    # 4) 连续对局：new_game 后再走
    ai.new_game()
    g4 = np.zeros((N, N), dtype=np.int8)
    g4[6, 6] = 1
    r4, c4, _ = ai.best_move(g4, 2, time_limit=0.8)
    print(f"重开后应招: {chr(65+c4)}{r4+1}")

    ai.stop()
    print("\nRapfi 协议测试通过 ✔")


if __name__ == "__main__":
    main()
