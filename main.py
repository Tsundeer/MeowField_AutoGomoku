# -*- coding: utf-8 -*-
"""兼容入口：python main.py 等价于 python -m meowfield_gomoku。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from meowfield_gomoku.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
