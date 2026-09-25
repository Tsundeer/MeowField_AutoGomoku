# -*- coding: utf-8 -*-
"""AI 引擎封装。

- RapfiAI：开源强引擎 Rapfi（Gomocup 冠军引擎，GPL-3.0），
  以子进程运行，走 Gomocup/piskvork 文本协议。
  协议交互与颜色无关：我方棋子标 type=1，对方标 type=2，
  因此我方执黑执白均可（含自动后手模式）。
- SimpleAI：纯 Python 内置引擎（engine.py），rapfi 缺失时的兜底。
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from .simple_engine import GomokuEngine as _GomokuEngine

from ... import config as C

def _locate_engines_dir() -> str:
    """engines/ 定位：打包后取 PyInstaller 解包目录；源码运行为仓库根。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return os.path.join(base, "engines")
        return os.path.join(os.path.dirname(sys.executable), "engines")
    # src/meowfield_gomoku/infrastructure/engine/ai_factory.py -> 仓库根
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "..", "..", "engines")


ENGINES_DIR = os.path.abspath(_locate_engines_dir())

MOVE_RE = re.compile(r"^\s*(\d{1,3})[ ,]+(\d{1,3})\s*$")


# 启动探测已验证：vnni/avx512 构建在部分 CPU 上会在搜索中崩溃，
# avx2 兼容性与性能最均衡，故放最前；sse 兜底。
_PREF_ORDER = ["avx2", "sse", "avxvnni", "avx512vnni", "avx512"]


def find_rapfi_exes():
    """返回候选 rapfi 可执行文件列表（按指令集从新到旧排序）。"""
    if not os.path.isdir(ENGINES_DIR):
        return []
    found = []
    for root, _dirs, files in os.walk(ENGINES_DIR):
        for f in files:
            if f.lower().endswith(".exe") and "rapfi" in f.lower():
                found.append(os.path.join(root, f))
    ordered = []
    for key in _PREF_ORDER:
        for p in found:
            if key in os.path.basename(p).lower() and p not in ordered:
                ordered.append(p)
    for p in found:
        if p not in ordered:
            ordered.append(p)
    return ordered


def find_rapfi_exe():
    exes = find_rapfi_exes()
    return exes[0] if exes else None


class RapfiAI:
    name = "rapfi"

    def __init__(self, size=13, log_fn=None, turn_time_ms=20000, threads=0):
        self.size = size
        self.turn_time_ms = turn_time_ms   # 每步思考预算（毫秒）
        self.threads = threads             # 0 = 用满全部逻辑核
        self.log = log_fn or (lambda s: None)
        self.proc = None
        self.lock = threading.Lock()
        self._last_speed_log = 0.0

    def _patch_config_threads(self):
        """把线程数写入引擎的 config.toml（仅在与当前值不同时改写）。"""
        import re
        path = os.path.join(ENGINES_DIR, "config.toml")
        try:
            if not os.path.isfile(path):
                return
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            new = re.sub(r"(?m)^default_thread_num\s*=\s*\d+",
                         f"default_thread_num = {int(self.threads)}", content)
            if new != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
                self.log(f"[rapfi] 已设置线程数: {int(self.threads)}"
                         f"{'（全部逻辑核）' if int(self.threads) == 0 else ''}")
        except Exception as e:
            self.log(f"[rapfi] 写入线程数失败（沿用引擎默认值）: {e}")

    # ---- 子进程管理 ----
    def start(self):
        candidates = find_rapfi_exes()
        if not candidates:
            raise FileNotFoundError(
                "未找到 rapfi 引擎，请将引擎解压到 engines/ 目录（见 README）")
        last_err = None
        for exe in candidates:
            try:
                if self._try_start(exe):
                    self.log(f"[rapfi] 引擎已启动: {os.path.basename(exe)}")
                    return
            except Exception as e:
                last_err = e
                self.log(f"[rapfi] {os.path.basename(exe)} 启动失败: {e}")
        raise RuntimeError(f"所有 rapfi 引擎均无法启动: {last_err}")

    def _expect_ok(self, timeout=10):
        """等待 START 的 OK 应答（MESSAGE 等噪声行跳过）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    raise RuntimeError("引擎进程已退出")
                time.sleep(0.01)
                continue
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith("ok"):
                return True
            if low.startswith("?"):
                raise RuntimeError(f"引擎报错: {line}")
            self.log(f"[rapfi] {line}")
        raise RuntimeError("引擎初始化无应答")

    def _try_start(self, exe):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
            self.proc = None
        self._patch_config_threads()
        self.proc = subprocess.Popen(
            [exe], cwd=os.path.dirname(exe),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1)
        # 初始化棋盘；无限制规则（休闲五子）
        self._send(f"START {self.size}")
        self._expect_ok(timeout=10)
        # 每步思考上限：真·不限时会在均势开局一路搜到深度 99
        # （实测单步 20 分钟以上），无法接受；预算给足后引擎算到
        # 必胜会提前落子，均势走满预算也远强于短时限。
        self._send("INFO timeout_match 0")
        self._send(f"INFO timeout_turn {self.turn_time_ms}")
        return True

    def stop(self):
        if self.proc:
            try:
                self._send("END")
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def _send(self, line):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()

    def _readline(self, timeout=None):
        """读引擎输出直到出现着法行（'x y' / 'x,y'）。

        MESSAGE/DEBUG/INFO/Speed 等噪声行全部忽略（转日志）；
        '?' 开头视为引擎报错。timeout=None 表示不限时（阻塞等待）。
        返回 None 表示超时或错误。
        """
        deadline = None if timeout is None else time.time() + timeout
        proc, out = self.proc, self.proc.stdout
        while deadline is None or time.time() < deadline:
            line = out.readline()
            if not line:
                if proc.poll() is not None:
                    return None
                time.sleep(0.01)
                continue
            line = line.strip()
            if not line:
                continue
            if line.startswith("?"):
                self.log(f"[rapfi] 错误应答: {line}")
                return None
            m = MOVE_RE.match(line)
            if m:
                return line
            # 搜索进度节流：Speed 行（每完成一层迭代）最多 3 秒记一条，
            # Depth 明细行不写日志，避免长考刷屏
            if line.startswith("Speed"):
                now = time.time()
                if now - self._last_speed_log > 3.0:
                    self._last_speed_log = now
                    self.log(f"[rapfi] {line}")
            elif line.startswith("MESSAGE"):
                self.log(f"[rapfi] {line}")
        return None

    # ---- 对局控制 ----
    def new_game(self):
        with self.lock:
            if not self.proc:
                self.start()
            else:
                self._send(f"START {self.size}")
                self._expect_ok(timeout=15)

    def best_move(self, grid, my_color, time_limit=None, **_):
        """grid: 13x13 (0空 1黑 2白)；不限时模式（启动时已配置）。
        返回 (r, c, info) 或 None。"""
        n = self.size
        # 空盘直接天元：注意必须在发送 BOARD 之前判断，
        # 否则 BOARD 缺少 DONE 会让引擎卡在读子循环。
        total = sum(int(v) for row in grid for v in row)
        if total == 0:
            m = n // 2
            return m, m, {"note": "开局天元"}
        with self.lock:
            if not self.proc:
                self.start()
            self._send("INFO rule 0")   # 自由规则（无禁手）
            self._send("BOARD")
            stones = 0
            for r in range(n):
                for c in range(n):
                    v = int(grid[r][c])
                    if v:
                        t = 1 if v == my_color else 2
                        self._send(f"{c},{r},{t}")   # 协议: x,y,t（逗号分隔）
                        stones += 1
            self._send("DONE")
            # 等待引擎自行完成（预算内必胜会秒下，均势走满预算）
            line = self._readline(timeout=max(60.0, self.turn_time_ms / 1000 * 3 + 30))
            if line is None:
                raise RuntimeError("rapfi 未在时限内返回着法")
            m = MOVE_RE.match(line)
            if not m:
                raise RuntimeError(f"rapfi 输出无法解析: {line!r}")
            x, y = int(m.group(1)), int(m.group(2))
            if not (0 <= x < n and 0 <= y < n):
                raise RuntimeError(f"rapfi 返回非法坐标: ({x},{y})")
            return y, x, {"engine": "rapfi"}


class SimpleAI:
    name = "simple"

    def __init__(self, size=13, log_fn=None):
        self.size = size
        self.log = log_fn or (lambda s: None)
        self.core = _GomokuEngine(size)

    def start(self):
        pass

    def stop(self):
        pass

    def new_game(self):
        self.core.reset()

    def best_move(self, grid, my_color, time_limit=None, max_depth=64, **_):
        # 内置引擎无限时模式下给个很大的上限，迭代加深会自行收敛
        res = self.core.best_move(grid, my_color,
                                  time_limit=time_limit if time_limit else 600,
                                  max_depth=max_depth)
        if res is None:
            return None
        r, c, info = res
        info["engine"] = "simple"
        return r, c, info


def create_ai(kind="auto", size=13, log_fn=None, turn_time_ms=None, threads=None):
    """kind: rapfi / simple / auto（优先 rapfi）。"""
    if kind in ("auto", "rapfi") and find_rapfi_exe():
        return RapfiAI(size=size, log_fn=log_fn,
                       turn_time_ms=turn_time_ms or C.RAPFI_TURN_TIME_MS,
                       threads=C.ENGINE_THREADS if threads is None else threads)
    if kind == "rapfi":
        raise FileNotFoundError("指定了 rapfi 引擎但未找到可执行文件")
    return SimpleAI(size=size, log_fn=log_fn)
