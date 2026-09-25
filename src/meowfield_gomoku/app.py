# -*- coding: utf-8 -*-
"""组合根（Composition Root）与进程入口。

职责（镜像 MeowField_AutoPiano 的 App.OnStartup）：
1. 尽早初始化文件日志；
2. 挂接全局异常钩子（记录 + 提示，不让进程无声崩溃）；
3. 装配服务：设置存储、窗口控制器、棋盘识别、自动对弈服务、主窗口；
4. 运行 UI 主循环；退出时收尾（停线程、停引擎、flush 日志）。

用法：
    python -m meowfield_gomoku
    meowfield-autogomoku        （pip install -e . 后）
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import subprocess
import sys
import threading

from . import __version__
from .infrastructure.storage.logging_setup import setup_logging
from .infrastructure.storage.settings_store import SettingsStore

logger = logging.getLogger("meowfield.app")

APP_TITLE = "MeowField_AutoGomoku"
USER_AGENT = f"MeowField-AutoGomoku/{__version__}"


def _excepthook(exc_type, exc, tb):
    logger.critical("未处理异常", exc_info=(exc_type, exc, tb))
    try:
        from tkinter import messagebox
        r = tk_root = None
        # 尝试在已有 Tk 实例上弹窗；失败则忽略（避免二次崩溃）
        import customtkinter as ctk
        if ctk.CTk._get_windows_instance():  # noqa: SLF001
            messagebox.showerror(APP_TITLE,
                                 f"发生未处理的错误，详情见日志：\n{exc}")
    except Exception:
        pass


def build_services():
    """装配所有服务（简单组合根；Windows 专用）。"""
    from .application.auto_play_service import AutoPlayService
    from .infrastructure.capture import windows as _w
    from .infrastructure.engine.ai_factory import create_ai
    from .infrastructure.storage.settings_store import SettingsStore
    from .infrastructure.vision.detector import BoardDetector

    _w.set_dpi_aware()

    class _WinController:
        """IWindowController 的过程式适配（Windows 实现）。"""
        find_game_window = staticmethod(_w.find_game_window)
        capture_client = staticmethod(_w.capture_client)
        focus_window = staticmethod(_w.focus_window)
        is_foreground = staticmethod(_w.is_foreground)
        move_mouse = staticmethod(_w.move_mouse)
        click_at = staticmethod(_w.click_at)
        get_cursor_pos = staticmethod(_w.get_cursor_pos)
        client_rect_screen = staticmethod(_w.client_rect_screen)

    class _EngineFactory:
        """延迟创建引擎（由 AutoPlayService 在首次需要时调用）。"""
        def __init__(self, settings: dict):
            self._settings = settings
            self._log = logging.getLogger("meowfield.engine")

        def __call__(self, kind, size, log_fn):
            return create_ai(kind, size, log_fn=log_fn,
                             turn_time_ms=None, threads=self._settings.get("engine_threads", 0))

    settings = SettingsStore().load()
    engine_factory = _EngineFactory(settings)

    player = AutoPlayService(
        our_color=settings.get("our_color", "auto"),
        engine_kind=settings.get("engine", "auto"),
        move_delay=settings.get("move_delay", 1.0),
        engine_threads=settings.get("engine_threads", 0),
        engine_factory=engine_factory,
    )
    detector = BoardDetector()
    controller = _WinController()
    return settings, player, detector, controller


_DECLINED_KEY = "MEOWFIELD_ADMIN_DECLINED"


def _has_relaunch_been_declined() -> bool:
    return os.environ.get(_DECLINED_KEY) == "1"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> bool:
    """以管理员身份重启自身（ShellExecute runas）。

    返回 True 表示已发起重启（当前进程应退出）；
    用户取消 UAC 返回 False，调用方降级为普通权限继续。
    """
    params = subprocess.list2cmdline(sys.argv)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1)  # SW_SHOWNORMAL
    return int(ret) > 32


def ensure_admin_or_relaunch() -> bool:
    """保证点击可送达游戏窗口：游戏常以管理员运行，普通权限进程的
    SendInput 会被 UIPI 拦截。

    返回 True=当前已是管理员；False=已发起提权重启（本进程应退出）或
    用户取消提权（降级为普通权限继续，但自动点击可能无效）。
    """
    log = logging.getLogger("meowfield.app")
    if is_admin():
        return True
    log.warning("当前为普通权限，请求管理员权限（UAC）…")
    if _relaunch_as_admin():
        log.info("已发起提权重启，本进程退出")
        return False
    os.environ[_DECLINED_KEY] = "1"
    log.warning("管理员提权被取消，降级为普通权限继续（自动点击可能无效）")
    return False


def main() -> int:
    setup_logging()
    sys.excepthook = _excepthook
    logger.info("%s v%s 启动", APP_TITLE, __version__)

    if is_admin():
        logger.info("以管理员权限运行")
    elif not _has_relaunch_been_declined() and _relaunch_as_admin():
        return 0  # 已发起提权重启，本进程退出
    else:
        logger.warning("未获得管理员权限，若游戏以管理员运行则自动点击将被系统拦截")

    try:
        settings, player, detector, controller = build_services()
    except Exception:
        logger.critical("服务装配失败", exc_info=True)
        return 1

    # UI：主窗口接管服务（棋盘识别线程在 AutoPlayService 中）
    try:
        from .ui.main_window import run_ui
        return run_ui(player=player, settings=settings)
    except Exception:
        logger.critical("界面初始化失败", exc_info=True)
        return 1
    finally:
        player.stop_event.set()
        logging.shutdown()


if __name__ == "__main__":
    sys.exit(main())
