# -*- coding: utf-8 -*-
"""棋盘识别标定工具：对截图（或游戏实时画面）运行识别并输出调试图。

用法：
  python tools/calibrate.py samples/board_1080p.png [更多图片...]
  python tools/calibrate.py --live        # 对当前游戏窗口截图识别
"""
import os
import sys
import time

import cv2

from meowfield_gomoku.infrastructure.vision import detector as det_mod
from meowfield_gomoku.infrastructure.storage.settings_store import app_data_dir

DBG = os.path.join(str(app_data_dir()), "debug")
os.makedirs(DBG, exist_ok=True)


def run(img, name):
    d = det_mod.BoardDetector()
    try:
        det = d.detect(img, with_overlay=True)
    except det_mod.BoardNotFound as e:
        print(f"[{name}] 识别失败: {e}")
        return
    out = os.path.join(DBG, f"calib_{name}_{time.strftime('%H%M%S')}.png")
    cv2.imwrite(out, det.overlay)
    print(f"[{name}] 面板: {det.panel}  间距: {det.spacing:.1f}px")
    for r, c, v in det.stones():
        mark = "黑" if v == 1 else "白"
        print(f"    {det_mod.coord_label(r, c)} = {mark}")
    if det.unknown:
        print(f"    未知点: {det.unknown}")
    print(f"    调试图: {out}")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    if args[0] == "--live":
        import window as win
        hwnd, title, proc = win.find_game_window()
        print(f"窗口: {title} ({proc})")
        img, _ = win.capture_client(hwnd)
        run(img, "live")
    else:
        for p in args:
            img = cv2.imread(p)
            if img is None:
                print(f"无法读取: {p}")
                continue
            run(img, os.path.splitext(os.path.basename(p))[0])


if __name__ == "__main__":
    main()
