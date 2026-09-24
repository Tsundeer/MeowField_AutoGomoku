# -*- coding: utf-8 -*-
"""MeowField 自动五子棋 - 主程序（CustomTkinter 深色界面）。

用法：python main.py
"""
import json
import os
import queue
import sys
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import config as C
import detector as det_mod
from auto_player import AutoPlayer
from gomoku_ai import find_rapfi_exe

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
ASSETS = os.path.join(PROJECT_ROOT, "assets")

COLOR_NAME = {1: "黑", 2: "白"}

BOARD_PX = 500
MARGIN = 30

C_BG_BOARD = "#EFD9A7"
C_LINE = "#9C7B53"
C_STAR = "#7d5f3f"


class App:
    def __init__(self, root):
        self.root = root
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        root.title("MeowField 自动五子棋 · 开放空间")
        root.geometry("1120x720")
        root.minsize(1060, 660)
        try:
            root.iconbitmap(os.path.join(ASSETS, "icon.ico"))
        except Exception:
            pass

        self.q_items = []
        self.last_det = None
        self.window_title = None
        self.our_color_ui = None
        self.play_status = None

        self._build_ui()

        cfg = self._load_config()
        self._apply_config(cfg)

        self.player = AutoPlayer(log_fn=None)
        self.player.set_params(
            our_color=self._seg_to_color(),
            engine_kind=self.var_engine.get(),
            move_delay=float(self.var_delay.get()),
            engine_threads=int(self.var_threads.get() or 0),
        )
        self.player.start()
        root.after(100, self._poll_queue)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI ----------------
    def _build_ui(self):
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=14, pady=10)

        # 左：棋盘
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.pack(side="left", fill="y", padx=(0, 12))
        self.canvas = tk.Canvas(left, width=BOARD_PX, height=BOARD_PX,
                                bg=C_BG_BOARD, highlightthickness=1,
                                highlightbackground="#8a7248", bd=0)
        self.canvas.pack()
        self.var_status = tk.StringVar(value="正在查找游戏窗口…")
        ctk.CTkLabel(left, textvariable=self.var_status, wraplength=BOARD_PX,
                     text_color="#a8a8a8", justify="left").pack(anchor="w", pady=(8, 0))

        # 右：控制 + 日志
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # 标题
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(head, text="⚫⚪ MeowField 自动五子棋",
                     font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ctk.CTkLabel(head, text="开放空间 · 自动识别与对弈助手（Rapfi 强引擎）",
                     text_color="#8f8f8f").pack(anchor="w")

        # 控制卡
        box = ctk.CTkFrame(right, corner_radius=14)
        box.pack(fill="x")

        row1 = ctk.CTkFrame(box, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(12, 4))
        self.btn_toggle = ctk.CTkButton(row1, text="▶  开始自动对弈", width=170,
                                        height=38,
                                        font=("Microsoft YaHei UI", 14, "bold"),
                                        fg_color="#2FA35C", hover_color="#278A4E",
                                        command=self._toggle_active)
        self.btn_toggle.pack(side="left")
        ctk.CTkButton(row1, text="📷 截图测试识别", width=130, height=38,
                      fg_color="#3A4A6B", hover_color="#44587F",
                      command=lambda: self.player.request_shot.set()).pack(
            side="left", padx=8)
        ctk.CTkButton(row1, text="打开调试目录", width=110, height=38,
                      fg_color="#3A3A42", hover_color="#4a4a54",
                      command=self._open_debug).pack(side="left")

        row2 = ctk.CTkFrame(box, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(row2, text="我方棋子颜色", text_color="#bdbdbd").pack(side="left")
        self.seg_color = ctk.CTkSegmentedButton(
            row2, values=["自动", "黑", "白"], height=30,
            command=self._on_setting_change)
        self.seg_color.set("自动")
        self.seg_color.pack(side="left", padx=(10, 0))

        ctk.CTkLabel(box, text="提示：轮到谁走由双方子数自动判断，与先后手颜色无关。\n"
                               "「自动」无需选择颜色：看到落子后即接管，并自动锁定你的棋子颜色；\n"
                               "开局第一手若轮到你，程序会自动下在中心 H7。",
                     text_color="#8f8f8f", justify="left",
                     font=("Microsoft YaHei UI", 11)).pack(anchor="w", padx=12,
                                                           pady=(4, 2))

        row3 = ctk.CTkFrame(box, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(2, 4))
        ctk.CTkLabel(row3, text="引擎", text_color="#bdbdbd").pack(side="left")
        engine_names = ["auto", "rapfi", "simple"]
        if find_rapfi_exe() is None:
            engine_names = ["auto", "simple"]
        self.var_engine = ctk.StringVar(value="auto")
        self.cmb_engine = ctk.CTkOptionMenu(
            row3, values=engine_names, variable=self.var_engine, width=90,
            height=28, command=lambda _v: self._on_setting_change())
        self.cmb_engine.pack(side="left", padx=(8, 14))

        ctk.CTkLabel(row3, text="线程数", text_color="#bdbdbd").pack(side="left")
        self.var_threads = ctk.StringVar(value="0")
        self.ent_threads = ctk.CTkEntry(row3, textvariable=self.var_threads,
                                        width=56, height=28, justify="center")
        self.ent_threads.pack(side="left", padx=(8, 14))
        self.ent_threads.bind("<FocusOut>", lambda _e: self._on_setting_change())

        ctk.CTkLabel(row3, text="落子停顿(秒)", text_color="#bdbdbd").pack(side="left")
        self.var_delay = ctk.StringVar(value="1.0")
        self.opt_delay = ctk.CTkOptionMenu(
            row3, values=["0.0", "0.5", "1.0", "1.5", "2.0", "3.0"],
            variable=self.var_delay, width=80, height=28,
            command=lambda _v: self._on_setting_change())
        self.opt_delay.pack(side="left", padx=(8, 0))

        self.var_engine_info = ctk.StringVar(value="")
        ctk.CTkLabel(box, textvariable=self.var_engine_info,
                     text_color="#8f8f8f").pack(anchor="w", padx=12, pady=(4, 8))

        # 日志卡
        logbox = ctk.CTkFrame(right, corner_radius=14)
        logbox.pack(fill="both", expand=True, pady=(10, 0))
        ctk.CTkLabel(logbox, text="运行日志", text_color="#bdbdbd").pack(
            anchor="w", padx=12, pady=(8, 0))
        self.txt_log = ctk.CTkTextbox(logbox, font=("Microsoft YaHei UI", 11),
                                      wrap="word", fg_color="#1b1b21",
                                      border_width=0)
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.txt_log.configure(state="disabled")

        self._draw_empty_board()

    def _draw_empty_board(self):
        self.canvas.delete("all")
        n = C.BOARD_N
        m, sp = MARGIN, (BOARD_PX - 2 * MARGIN) / (n - 1)
        # 木纹底：交替色条
        for i in range(12):
            y0 = BOARD_PX * i / 12
            shade = "#EFD9A7" if i % 2 == 0 else "#EAD2A0"
            self.canvas.create_rectangle(0, y0, BOARD_PX, y0 + BOARD_PX / 12 + 1,
                                         outline="", fill=shade)
        for i in range(n):
            x = m + i * sp
            self.canvas.create_line(x, m, x, m + (n - 1) * sp, fill=C_LINE)
            self.canvas.create_line(m, x, m + (n - 1) * sp, x, fill=C_LINE)
        # 星位
        for i, j in [(3, 3), (3, 9), (9, 3), (9, 9), (6, 6)]:
            x, y = m + j * sp, m + i * sp
            r = max(2, sp * 0.09)
            self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                    fill=C_STAR, outline="")
        self._grid_geom = (m, sp)

    def draw_board(self, det):
        """根据检测结果绘制棋盘。"""
        self._draw_empty_board()
        margin, sp = self._grid_geom
        board = det.board
        n = board.shape[0]
        for r in range(n):
            for c in range(n):
                v = board[r, c]
                if not v:
                    continue
                x, y = margin + c * sp, margin + r * sp
                rr = sp * 0.44
                if v == 1:
                    self.canvas.create_oval(x - rr, y - rr, x + rr, y + rr,
                                            fill="#111114", outline="#000")
                    self.canvas.create_oval(x - rr * 0.45, y - rr * 0.5,
                                            x + rr * 0.05, y + rr * 0.05,
                                            fill="#4a4a52", outline="")
                else:
                    self.canvas.create_oval(x - rr, y - rr, x + rr, y + rr,
                                            fill="#f7f7f9", outline="#8d8d92")
                    self.canvas.create_oval(x - rr * 0.45, y - rr * 0.5,
                                            x + rr * 0.05, y + rr * 0.05,
                                            fill="#ffffff", outline="")
        # 待确认落子蓝圈
        if getattr(self.player, "awaiting", None):
            ar, ac = self.player.awaiting
            x, y = margin + ac * sp, margin + ar * sp
            self.canvas.create_oval(x - sp * 0.52, y - sp * 0.52,
                                    x + sp * 0.52, y + sp * 0.52,
                                    outline="#3d8bff", width=2)
        # 坐标标签
        for i in range(n):
            self.canvas.create_text(margin + i * sp, MARGIN - 14,
                                    text=chr(ord("A") + i),
                                    font=("Segoe UI", 8), fill="#7a5c38")
            self.canvas.create_text(MARGIN - 14, margin + i * sp,
                                    text=str(i + 1), font=("Segoe UI", 8),
                                    fill="#7a5c38")

    # ---------------- 行为 ----------------
    def _toggle_active(self):
        new_active = not self.player.active
        if new_active and self.player.confirmed is None:
            messagebox.showinfo(
                "提示", "尚未识别到棋盘。请先进入游戏的五子棋对局界面，\n"
                        "点「截图测试识别」确认能识别后再开始。")
            return
        self.player.set_params(active=new_active)
        self._update_toggle_btn()

    def _update_toggle_btn(self):
        if self.player.active:
            self.btn_toggle.configure(text="■  停止自动对弈",
                                      fg_color="#C43C3C", hover_color="#A83232")
        else:
            self.btn_toggle.configure(text="▶  开始自动对弈",
                                      fg_color="#2FA35C", hover_color="#278A4E")

    def _seg_to_color(self):
        return {"自动": "auto", "黑": "1", "白": "2"}.get(self.seg_color.get(), "auto")

    def _on_setting_change(self, *_a):
        try:
            threads = int(self.var_threads.get() or 0)
        except ValueError:
            threads = 0
        self.player.set_params(
            our_color=self._seg_to_color(),
            engine_kind=self.var_engine.get(),
            move_delay=float(self.var_delay.get()),
            engine_threads=threads,
        )
        self._save_config()

    def _open_debug(self):
        d = os.path.join(PROJECT_ROOT, "debug")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    # ---------------- 队列轮询 ----------------
    def _poll_queue(self):
        try:
            while True:
                item = self.player.q.get_nowait()
                self._handle_event(item)
        except queue.Empty:
            pass
        except Exception as e:
            self._log(f"UI处理异常: {e}")
        self.root.after(120, self._poll_queue)

    def _handle_event(self, item):
        kind = item[0]
        if kind == "log":
            self._log(item[1])
        elif kind == "board":
            self.last_det = item[1]
            self.draw_board(item[1])
            if not self.player.active:
                self.var_status.set(
                    f"识别正常：{int((item[1].board > 0).sum())} 颗子"
                    f"（未开启自动落子）")
        elif kind == "window":
            self.window_title = item[1]
        elif kind == "shot":
            path, det = item[1], item[2]
            if path:
                self._log(f"截图已保存: {path}")
            if det is not None:
                self.last_det = det
                self.draw_board(det)
        elif kind == "active":
            self._update_toggle_btn()
        elif kind == "our_color":
            self.our_color_ui = item[1]
        elif kind == "engine":
            name = item[1]
            extra = "（开源强引擎）" if name == "rapfi" else "（内置简易引擎）"
            self.var_engine_info.set(f"引擎已就绪: {name}{extra}")
        elif kind == "status":
            self.play_status = item[1]
        self._refresh_status()

    def _refresh_status(self):
        extra = ""
        if self.our_color_ui:
            extra += f" | 我方执{COLOR_NAME.get(self.our_color_ui, '?')}"
            self.our_color_ui = None
        title = getattr(self, "window_title", None)
        parts = [f"窗口: {title or '未找到'}"]
        if extra:
            parts.append(extra.strip(" |"))
        if getattr(self, "play_status", None):
            parts.append(self.play_status)
            self.play_status = None
        self.var_status.set("  ·  ".join(p for p in parts if p))

    def _log(self, s):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", s + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    # ---------------- 配置 ----------------
    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _apply_config(self, cfg):
        color = cfg.get("our_color", "auto")
        self.seg_color.set({"auto": "自动", "1": "黑", "2": "白"}.get(color, "自动"))
        if cfg.get("engine") in ("auto", "rapfi", "simple"):
            self.var_engine.set(cfg["engine"])
        try:
            self.var_delay.set(str(float(cfg.get("move_delay", 1.0))))
        except Exception:
            pass
        try:
            self.var_threads.set(str(max(0, int(cfg.get("engine_threads", 0)))))
        except Exception:
            pass

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "our_color": self._seg_to_color(),
                    "engine": self.var_engine.get(),
                    "move_delay": self.var_delay.get(),
                    "engine_threads": self.var_threads.get(),
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self):
        try:
            self.player.stop_event.set()
            self._save_config()
        finally:
            self.root.after(150, self.root.destroy)


def main():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    root = ctk.CTk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
