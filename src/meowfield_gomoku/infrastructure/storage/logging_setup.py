# -*- coding: utf-8 -*-
"""日志基础设施：按日滚动的文件日志 + 可选控制台输出。

镜像 MeowField_AutoPiano 的 Serilog 约定：
  %LocalAppData%\\MeowField_AutoGomoku\\logs\\app-YYYYMMDD.log，保留 14 天。
"""
from __future__ import annotations

import logging
import logging.handlers

from .settings_store import logs_dir

LOG_FORMAT = "%(asctime)s [%(levelname).1s] %(name)s: %(message)s"


def setup_logging(level=logging.INFO, console: bool = False) -> logging.Handler:
    """初始化根日志：按日滚动文件（保留 14 份）。返回文件 handler。"""
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return root.handlers[0]
    fmt = logging.Formatter(LOG_FORMAT)

    fh = logging.handlers.TimedRotatingFileHandler(
        logs_dir() / "app.log", when="midnight", backupCount=14,
        encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)
    return fh


class QueueLogHandler(logging.Handler):
    """把日志记录转发到队列（UI 日志面板消费）。"""

    def __init__(self, sink):
        super().__init__()
        self.sink = sink

    def emit(self, record):
        try:
            self.sink(record)
        except Exception:
            pass
