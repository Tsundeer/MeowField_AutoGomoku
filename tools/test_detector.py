# -*- coding: utf-8 -*-
"""识别器离线测试：基准识别 + 多分辨率 + 合成棋子回读。

用法：python tools/test_detector.py
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import detector as det_mod  # noqa: E402

SAMPLE = os.path.join(ROOT, "samples", "board_1080p.png")
DBG = os.path.join(ROOT, "debug")
os.makedirs(DBG, exist_ok=True)

fails = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name} {detail}")
    if not cond:
        fails.append(name)


def stones_str(board):
    return {det_mod.coord_label(int(r), int(c)): int(v)
            for r, c in zip(*np.where(board > 0))
            for v in [board[r, c]]}


def run_case(name, img, expect):
    det = det_mod.BoardDetector()
    try:
        d = det.detect(img, with_overlay=True)
    except det_mod.BoardNotFound as e:
        check(f"{name}: 识别成功", False, f"({e})")
        return None
    got = stones_str(d.board)
    check(f"{name}: 识别成功", True, f"stones={got}")
    check(f"{name}: 石子一致", got == expect, f"got={got} expect={expect}")
    check(f"{name}: 无未知点", len(d.unknown) == 0, f"unknown={d.unknown}")
    h, w = img.shape[:2]
    cv2.imwrite(os.path.join(DBG, f"test_{name}.png"),
                cv2.resize(d.overlay, (w // 2, h // 2)))
    return d


def draw_stone(img, x, y, sp, color):
    """模拟真实棋子：带描边与简单阴影的圆。color: 1黑 2白。"""
    radius = int(sp * 0.42)
    shadow = (int(sp * 0.13), int(sp * 0.13))
    cv2.ellipse(img, (x + shadow[0], y + shadow[1]),
                (radius, int(radius * 0.75)), 0, 0, 360,
                (150, 160, 170), -1, cv2.LINE_AA)
    if color == 2:
        cv2.circle(img, (x, y), radius, (222, 224, 228), -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), radius, (140, 140, 145), 2, cv2.LINE_AA)
        cv2.ellipse(img, (x - radius // 3, y - radius // 3),
                    (radius // 2, radius // 3), -30, 0, 360,
                    (245, 246, 248), -1, cv2.LINE_AA)
    else:
        cv2.circle(img, (x, y), radius, (52, 48, 45), -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), radius, (25, 22, 20), 2, cv2.LINE_AA)
        cv2.ellipse(img, (x - radius // 3, y - radius // 3),
                    (radius // 2, radius // 3), -30, 0, 360,
                    (110, 105, 100), -1, cv2.LINE_AA)


def main():
    img0 = cv2.imread(SAMPLE)
    base_expect = {"G7": 2}

    # 1) 原图
    d0 = run_case("原图1080p", img0, base_expect)
    if d0 is None:
        sys.exit(1)
    pts = d0.points.copy()
    sp = d0.spacing

    # 2) 多分辨率
    for tag, ratio in (("720p", 720 / 1107), ("1440p", 1440 / 1107),
                       ("900p", 900 / 1107)):
        w = int(round(img0.shape[1] * ratio))
        h = int(round(img0.shape[0] * ratio))
        img = cv2.resize(img0, (w, h), interpolation=cv2.INTER_AREA)
        run_case(tag, img, base_expect)

    # 3) 合成棋子回读（多颗黑/白随机分布）
    rng = np.random.default_rng(7)
    for trial in range(3):
        img = img0.copy()
        expect = dict(base_expect)  # 底图原有 G7 白子
        cells = [(r, c) for r in range(13) for c in range(13)]
        rng.shuffle(cells)
        picked = cells[:16]
        for i, (r, c) in enumerate(picked):
            color = 1 if i % 2 == 0 else 2
            x, y = pts[r, c]
            draw_stone(img, int(x), int(y), sp, color)
            expect[det_mod.coord_label(r, c)] = color
        # 底下那颗真子（G7白）若被覆盖则以覆盖后的为准
        run_case(f"合成棋子#{trial+1}", img, expect)

    print()
    if fails:
        print(f"共 {len(fails)} 项失败: {fails}")
        sys.exit(1)
    print("全部通过 ✔")


if __name__ == "__main__":
    main()
