# -*- coding: utf-8 -*-
"""自动对弈状态机（后台线程）。

核心规则（不依赖"先手=某种颜色"的假设，颜色先后手均适用）：

1. 轮次判定：五子棋严格轮流，**子少的一方行棋**（子数相等说明轮到
   先行方，若历史缺失则先观察一次落子再判定）。
2. 我方颜色：不以颜色推轮次。程序点击后棋盘上出现的棋子颜色即我方
   颜色（铁证）；点击未生效时按"首次观测到的落子是你手动所下"回退。
3. 接管：开启自动后随时可接管中盘局面——子数可判轮次时立即行动；
   不能判时等下一次落子（对方下完必轮到我方）。
4. 防幻影：落子前鼠标移到目标点复核，排除悬停半透明预览子。
5. 点击加固：校验前台窗口（失败重试并预热点击），点击后等棋盘确认，
   超时自动重试。
"""
import logging
import random
import queue
import threading
import time

import numpy as np

from .. import config as C
from ..domain.board import coord_label
from ..infrastructure.vision import detector as det_mod
from ..infrastructure.capture import windows as win
from ..infrastructure.engine.ai_factory import create_ai

COLOR_NAME = {1: "黑", 2: "白"}

logger = logging.getLogger("meowfield.play")


class AutoPlayService(threading.Thread):
    """自动对弈服务：识别轮询 + 回合状态机 + 自动落子（后台线程）。

    通过 engine_factory 注入引擎创建（依赖倒置），便于测试替换。
    """

    def __init__(self, our_color="auto", engine_kind="auto",
                 move_delay=1.0, engine_threads=None, save_shots=True,
                 log_fn=None, engine_factory=None, think_limit=None):
        super().__init__(daemon=True)
        self.our_color_opt = our_color        # "auto" / "1" / "2"
        self.engine_kind = engine_kind
        self.move_delay = move_delay
        self.engine_threads = int(engine_threads) if engine_threads is not None else None
        self.think_limit = float(think_limit) if think_limit else None
        self.save_shots = save_shots
        self.q = queue.Queue()
        self._log_ext = log_fn
        self.stop_event = threading.Event()
        self.active = False
        self.request_shot = threading.Event()

        self._engine_factory = engine_factory
        self._log_ext = log_fn or (lambda msg: logger.info(msg))
        self.detector = det_mod.BoardDetector()
        self.ai = None
        self.hwnd = None
        self.origin = (0, 0)
        self.client_size = (0, 0)

        self.confirmed = None       # np 13x13 已确认局面
        self.last_read = None
        self.same_count = 0
        self.expected_next = None   # 下一个行棋方（1黑/2白），None=暂无法判定
        self.our_color = None if our_color == "auto" else int(our_color)
        self.color_locked = False   # True=已通过本程序点击的棋子确认颜色
        self.learning_move = False  # 正在进行"首次接管"的试探落子
        self.awaiting = None        # (r,c) 已点击待确认
        self.await_deadline = 0
        self.click_retried = 0
        self.lost_count = 0
        self.busy = False
        self.thinking = False       # 引擎后台思考中
        self._opening_tried = False # 本局是否已尝试过先手开局（中心）
        self._think_done = threading.Event()
        self._think_result = None
        self._think_err = None
        self._think_board = None
        self._last_points = None

    # ---------- 工具 ----------
    def log(self, msg):
        self.q.put(("log", time.strftime("%H:%M:%S ") + msg))
        if self._log_ext:
            self._log_ext(msg)

    def set_params(self, our_color=None, engine_kind=None,
                   move_delay=None, engine_threads=None, active=None,
                   think_limit=None):
        if our_color is not None:
            self.our_color_opt = our_color
            new_color = None if our_color == "auto" else int(our_color)
            if new_color != self.our_color:
                self.our_color = new_color
                self.color_locked = False
                if new_color:
                    self.log(f"已指定我方棋子颜色：{COLOR_NAME[new_color]}"
                             f"（以游戏中你的棋子为准）")
                    self._recheck_turn()
        if engine_kind is not None and engine_kind != self.engine_kind:
            self.engine_kind = engine_kind
            self._restart_ai()
        if move_delay is not None:
            self.move_delay = move_delay
        if engine_threads is not None and int(engine_threads) != (self.engine_threads or 0):
            self.engine_threads = int(engine_threads)
            self._restart_ai()
        if think_limit is not None:
            self.think_limit = float(think_limit) if float(think_limit) > 0 else None
        if active is not None:
            if active and not self.active:
                self.active = True
                self.q.put(("active", True))
                self.log("自动落子已开启")
                self._log_turn_status()
                # 若当前已轮到我方，立即出手接管
                self._maybe_act()
            elif not active and self.active:
                self.active = False
                self.q.put(("active", False))
                self.log("自动落子已暂停")

    def _restart_ai(self):
        if self.ai:
            try:
                self.ai.stop()
            except Exception:
                pass
            self.ai = None

    def _ensure_ai(self):
        if self.ai is None:
            factory = self._engine_factory or (
                lambda kind, size, log_fn: create_ai(kind, size, log_fn=log_fn,
                                                     threads=self.engine_threads))
            self.ai = factory(self.engine_kind, C.BOARD_N, self.log)
            self.ai.start()
            self.q.put(("engine", type(self.ai).name))
        return self.ai

    # ---------- 轮次判定 ----------
    @staticmethod
    def _mover_by_counts(board):
        """子少的一方行棋；相等（轮到先行方）且历史未知时返回 None。"""
        b = int((board == 1).sum())
        w = int((board == 2).sum())
        if b == w:
            return None
        return 1 if b < w else 2

    def _log_turn_status(self):
        if self.confirmed is None:
            return
        b = int((self.confirmed == 1).sum())
        w = int((self.confirmed == 2).sum())
        mover = self._mover_by_counts(self.confirmed)
        if self.expected_next is not None:
            mover = self.expected_next
        if mover is None:
            self.log(f"当前局面：黑{b} 白{w}，轮到先行方"
                     f"（等待下一次落子后自动判定）")
        else:
            ours = "（轮到我方）" if mover == self.our_color else ""
            self.log(f"当前局面：黑{b} 白{w}，当前轮到：{COLOR_NAME[mover]}{ours}")

    def _recheck_turn(self):
        """颜色/局面变化后重算轮次，若轮到我方且自动已开启则接管。"""
        if self.confirmed is None:
            return
        by_counts = self._mover_by_counts(self.confirmed)
        if self.expected_next is None:
            self.expected_next = by_counts
        if self.active:
            self._log_turn_status()
            self._maybe_act()

    # ---------- 主循环 ----------
    def run(self):
        while not self.stop_event.is_set():
            loop_t = time.time()
            try:
                self._once()
            except Exception as e:
                self.log(f"识别线程异常: {e}")
                time.sleep(1.0)
            wait = C.POLL_INTERVAL - (time.time() - loop_t)
            if wait > 0:
                self.stop_event.wait(wait)
        self._restart_ai()

    def _once(self):
        if self.hwnd is None:
            try:
                self.hwnd, title, proc = win.find_game_window()
                self.log(f"已找到游戏窗口: {title} ({proc})")
                self.q.put(("window", title))
            except RuntimeError as e:
                self.q.put(("window", None))
                self._log_throttled(str(e))
                time.sleep(1.5)
                return
        try:
            frame, self.origin = win.capture_client(self.hwnd)
            self.client_size = (frame.shape[1], frame.shape[0])
        except Exception as e:
            self._log_throttled(f"截屏失败: {e}")
            return

        with_overlay = self.request_shot.is_set()
        try:
            det = self.detector.detect(frame, with_overlay=with_overlay)
        except det_mod.BoardNotFound as e:
            self.lost_count += 1
            if self.lost_count == 3:
                self.log(f"未识别到棋盘（{e}）。请进入五子棋对局界面，"
                         f"并避免窗口被完全遮挡。")
            if with_overlay:
                path = self._save_image(frame, "raw")
                self.q.put(("shot", path, None))
                self.request_shot.clear()
            return
        self.lost_count = 0

        if with_overlay:
            path = self._save_image(det.overlay, "detect")
            self.q.put(("shot", path, det))
            self.request_shot.clear()

        self.q.put(("board", det))
        self._last_det = det

        board = det.board
        if self.last_read is not None and np.array_equal(board, self.last_read):
            self.same_count += 1
        else:
            self.last_read = board
            self.same_count = 1
        if self.same_count < C.STABLE_READS:
            return

        stable = board.copy()
        if self.confirmed is None or not np.array_equal(stable, self.confirmed):
            self._process_change(stable)
        if self.thinking and self._think_done.is_set():
            self._finish_think()
        self._check_click_timeout()

    # ---------- 局面变化处理 ----------
    def _process_change(self, stable):
        old = self.confirmed
        self.confirmed = stable
        if old is None:
            self.log(f"初始局面已锁定：{int((stable > 0).sum())} 颗子")
            self.expected_next = self._mover_by_counts(stable)
            self._log_turn_status()
            if self.active:
                self._maybe_act()
            return

        diff = np.argwhere(old != stable)
        old_stones = int((old > 0).sum())
        new_stones = int((stable > 0).sum())

        if new_stones < old_stones or len(diff) > 3:
            self.log(f"棋盘重置/大幅变化（{old_stones} -> {new_stones} 子），按新对局处理")
            self.awaiting = None
            self.learning_move = False
            self._opening_tried = False   # 新对局重新允许先手开局
            if self.our_color_opt == "auto":
                # 新对局颜色可能变化，重新学习
                self.our_color = None
                self.color_locked = False
            self.expected_next = self._mover_by_counts(stable)
            if self.ai:
                try:
                    self.ai.new_game()
                except Exception as e:
                    self.log(f"引擎重置失败: {e}")
            self._log_turn_status()
            if self.active:
                self._maybe_act()
            return

        placements = [(int(r), int(c), int(stable[r, c]))
                      for r, c in diff if old[r, c] == 0 and stable[r, c] != 0]
        if not placements:
            self.log("棋盘出现非正常变化，已重新同步")
            return

        # 悬停预览过滤：新"落子"若正好出现在鼠标所在交叉点，先移开鼠标复核
        if len(placements) == 1 and self._filter_preview(*placements[0]):
            return

        # 时序修正：本程序点击的落子必然先于对方的应招出现，
        # 必须最先处理，否则"我方确认+对方快招"在同一批差分里时
        # 会把轮次判断覆盖错，导致机器人误以为还没轮到自己而停摆。
        if self.awaiting is not None:
            placements.sort(key=lambda p: 0 if (p[0], p[1]) == self.awaiting else 1)

        for r, c, color in placements:
            self._handle_placement(r, c, color)

        if self.active and self.expected_next is not None \
                and self.expected_next == self.our_color:
            self._maybe_act()

    def _filter_preview(self, r, c, color=None):
        """新"落子"若正好出现在鼠标所在交叉点，疑似悬停预览子：
        移开鼠标重拍复核。返回 True 表示判定为预览已忽略（已采纳真实局面）。"""
        try:
            cur = win.get_cursor_pos()
            det = getattr(self, "_last_det", None)
            if cur is None or det is None or self.awaiting is not None:
                return False
            fx, fy = cur[0] - self.origin[0], cur[1] - self.origin[1]
            pts = det.points
            d2 = (pts[:, :, 0] - fx) ** 2 + (pts[:, :, 1] - fy) ** 2
            rr, cc = np.unravel_index(int(np.argmin(d2)), d2.shape)
            if d2[rr, cc] > (det.spacing * 0.55) ** 2:
                return False            # 鼠标不在棋盘交叉点附近
            if (int(rr), int(cc)) != (r, c):
                return False            # 新子不在鼠标处 -> 真实落子
            # 复核：移开鼠标重拍
            win.move_mouse(self.origin[0] + self.client_size[0] // 2,
                           self.origin[1] + 8)
            time.sleep(C.VERIFY_HOVER_DELAY)
            frame, origin = win.capture_client(self.hwnd)
            det2 = self.detector.detect(frame)
            self.origin = origin
            self._last_det = det2
            self.q.put(("board", det2))
            if det2.board[r, c] == 0:
                self.confirmed = det2.board.copy()
                self.log(f"忽略 {det_mod.coord_label(r, c)} 处的疑似悬停预览"
                         f"（请尽量让鼠标离开棋盘区域）")
                return True
            return False                # 鼠标移开后仍在 -> 真实落子
        except Exception:
            return False

    def _handle_placement(self, r, c, color):
        label = det_mod.coord_label(r, c)
        # 1) 本程序点击的棋子出现 -> 颜色铁证
        if self.awaiting == (r, c):
            self.awaiting = None
            self.click_retried = 0
            if self.our_color is not None and color != self.our_color \
                    and self.color_locked:
                self.log(f"警告：点击后棋子颜色({COLOR_NAME[color]})与记录不符，已纠正")
            if color != self.our_color:
                self.our_color = color
            self.color_locked = True
            self.learning_move = False
            self.log(f"我方落子 {label} 已确认（我方执{COLOR_NAME[color]}，已锁定）")
            self.expected_next = 3 - color
            return
        # 2) 颜色已知
        if self.our_color is not None:
            if color == self.our_color:
                self.log(f"检测到我方手动落子 {label}，继续接管后续着法")
                self.expected_next = 3 - color
            else:
                self.log(f"对方落子 {label}")
                self.expected_next = 3 - color
            return
        # 3) 颜色未知（自动学习）：把这次落子当作对方的应招来接管。
        #    若其实是你手动所下（还没轮到程序），点击会不生效，
        #    程序随后会自动纠正为我方颜色并等待对方落子。
        self.our_color = 3 - color
        self.learning_move = True
        self.expected_next = self.our_color
        self.log(f"观测到落子 {label}（{COLOR_NAME[color]}）：程序以"
                 f"{COLOR_NAME[self.our_color]}接管应招；若点击未生效"
                 f"（说明这步是你手动下的），会自动纠正颜色并等待对方落子")
        self.q.put(("our_color", self.our_color))

    # ---------- 落子 ----------
    def _maybe_act(self, initial=False):
        if self.busy or self.thinking or not self.active \
                or self.awaiting is not None or self.confirmed is None:
            return

        # 先手开局（对应"先手第一步下中间"的套路）：
        # 空盘时第一步必然轮到先手方，直接点中心 H7。
        # 若实际还没轮到我方，点击不会生效，超时后自动回退等待。
        if int((self.confirmed > 0).sum()) == 0 and not self._opening_tried:
            self._opening_tried = True
            self.learning_move = self.our_color is None
            self.log("先手开局：落子中心 H7"
                     + ("（落子成功后自动锁定我方颜色）" if self.learning_move else ""))
            if self._click_cell(6, 6):
                self.awaiting = (6, 6)
                self.await_deadline = time.time() + C.CLICK_TIMEOUT
                self.click_retried = 0
            return

        if self.our_color is None or self.expected_next is None:
            return
        if self.expected_next != self.our_color:
            return
        self.busy = True
        self.thinking = True
        self._think_done.clear()
        self._think_result = None
        self._think_err = None
        self._think_board = self.confirmed.copy()
        self.q.put(("status", "思考中…"))
        threading.Thread(target=self._think_worker, daemon=True).start()

    def _think_worker(self):
        """后台思考（不限时），完成时置 _think_done，由轮询线程收尾点击。
        轮询与界面刷新在思考期间照常运行。"""
        try:
            delay = random.uniform(0.7, 1.3) * max(0.0, self.move_delay)
            end = time.time() + delay
            while time.time() < end and not self.stop_event.is_set():
                time.sleep(0.1)
            if self.stop_event.is_set():
                self._think_result = None
                return
            ai = self._ensure_ai()
            t0 = time.time()
            res = ai.best_move(self._think_board, self.our_color,
                               time_limit=self.think_limit)
            self._think_result = res
            self._think_time = time.time() - t0
        except Exception as e:
            self._think_err = e
        finally:
            self._think_done.set()

    def _finish_think(self):
        """思考完成（轮询线程中调用）：校验局面后点击落子。"""
        self._think_done.clear()
        self.thinking = False
        self.busy = False
        if self._think_err is not None:
            self.log(f"引擎思考出错: {self._think_err}")
            return
        res = self._think_result
        if res is None:
            self.log("引擎无着法可下（棋盘已满？）")
            return
        if not np.array_equal(self._think_board, self.confirmed):
            self.log("思考期间局面发生变化，重新计算…")
            self._maybe_act()
            return
        r, c, info = res
        label = det_mod.coord_label(r, c)
        eng_name = info.get("engine", "?")
        extra = f", 深度{info['depth']}" if "depth" in info else ""
        self.log(f"我方选择 {label}（{eng_name}{extra}, "
                 f"思考{int(getattr(self, '_think_time', 0) * 1000)}ms）")

        # 防幻影：确认对方刚下的子是真实棋子而非悬停预览
        if not self._verify_no_ghost(r, c):
            return

        if not self._click_cell(r, c):
            return
        self.awaiting = (r, c)
        self.await_deadline = time.time() + C.CLICK_TIMEOUT
        self.click_retried = 0

    def _verify_no_ghost(self, target_r, target_c):
        """鼠标移到目标点，重拍确认对方刚下的子是真实棋子而非悬停预览。

        返回 True 表示可以继续点击目标点；False 表示疑似预览，已回滚状态。
        """
        try:
            sx, sy = self._screen_point(target_r, target_c, refresh=True)
        except Exception:
            return True  # 拿不到坐标就跳过校验
        win.move_mouse(sx, sy)
        time.sleep(C.VERIFY_HOVER_DELAY)
        try:
            frame, origin = win.capture_client(self.hwnd)
            det2 = self.detector.detect(frame)
        except Exception:
            return True
        self.q.put(("board", det2))
        if self.confirmed is not None:
            ghost = [(int(r), int(c)) for r, c in
                     np.argwhere((self.confirmed > 0) & (det2.board == 0))
                     if (int(r), int(c)) != (target_r, target_c)]
            if ghost:
                labels = [det_mod.coord_label(r, c) for r, c in ghost]
                self.log(f"{'、'.join(labels)} 处的棋子在复核时消失，"
                         f"疑似鼠标悬停预览，忽略本次落子")
                self.expected_next = 3 - self.our_color if self.our_color else None
                # 移开鼠标避免残影影响后续识别，然后采用真实局面
                win.move_mouse(origin[0] + self.client_size[0] // 2,
                               origin[1] + 8)
                time.sleep(C.VERIFY_HOVER_DELAY)
                try:
                    frame3, _ = win.capture_client(self.hwnd)
                    det3 = self.detector.detect(frame3)
                    self.confirmed = det3.board.copy()
                    self.q.put(("board", det3))
                except Exception:
                    self.confirmed = det2.board.copy()
                    for r, c in ghost:
                        self.confirmed[r, c] = 0
                return False
        return True

    def _click_cell(self, r, c):
        try:
            sx, sy = self._screen_point(r, c, refresh=True)
        except Exception as e:
            self.log(f"计算点击坐标失败: {e}")
            return False
        try:
            win.focus_window(self.hwnd)
            time.sleep(0.1)
        except Exception:
            pass
        # 前台校验失败时先在棋盘外安全点预热点击（避免激活点击被吞）
        if not win.is_foreground(self.hwnd):
            try:
                win.focus_window(self.hwnd)
                time.sleep(0.1)
            except Exception:
                pass
            if not win.is_foreground(self.hwnd):
                nx = self.origin[0] + self.client_size[0] // 2
                ny = self.origin[1] + 8
                self.log("窗口未在前台，先预热点击一次")
                win.click_at(nx, ny)
                time.sleep(0.15)
        win.click_at(sx, sy, hold=C.CLICK_HOLD)
        self.log(f"已点击 {det_mod.coord_label(r, c)}，等待棋盘确认…")
        return True

    def _screen_point(self, r, c, refresh=False):
        """交叉点的屏幕坐标；refresh=True 时重新截屏获取最新 points。"""
        if refresh:
            frame, origin = win.capture_client(self.hwnd)
            det = self.detector.detect(frame)
            self.origin = origin
            self._last_points = det.points
        pts = getattr(self, "_last_points", None)
        if pts is None:
            raise RuntimeError("尚无交叉点坐标")
        x, y = pts[r, c]
        return int(self.origin[0] + x), int(self.origin[1] + y)

    def _check_click_timeout(self):
        if self.awaiting is None or time.time() < self.await_deadline:
            return
        r, c = self.awaiting
        if self.confirmed[r, c] != 0:
            self.awaiting = None
            return
        label = det_mod.coord_label(r, c)
        # 自动学习的首次试探落子未生效：那次观测到的落子应是你手动所下
        if self.learning_move and not self.color_locked and self.our_color is not None:
            observed = 3 - self.our_color
            self.awaiting = None
            self.learning_move = False
            self.click_retried = 0
            self.our_color = observed
            self.expected_next = 3 - observed
            self.q.put(("our_color", self.our_color))
            self.log(f"点击未生效：判定首次落子为你手动所下，"
                     f"我方颜色已锁定为{COLOR_NAME[observed]}，"
                     f"等待对方落子后自动接管")
            return
        # 开局试探（空盘中心）未生效：还没轮到我方
        if self.learning_move and self.our_color is None:
            self.awaiting = None
            self.learning_move = False
            self.click_retried = 0
            self.log("开局试探未生效（还没轮到我方），等待对方落子后自动接管")
            return
        if self.click_retried < C.CLICK_RETRIES:
            self.click_retried += 1
            self.log(f"{label} 未确认（{self.click_retried}/{C.CLICK_RETRIES}），重试点击…")
            if self._click_cell(r, c):
                self.await_deadline = time.time() + C.CLICK_TIMEOUT
                return
        self.awaiting = None
        self.click_retried = 0
        self.giveups = getattr(self, "giveups", 0) + 1
        if self.giveups >= 3:
            self.expected_next = None
            self.log("连续多次落子未生效，已暂停自动出手。"
                     "请检查游戏窗口是否被遮挡/是否弹窗，"
                     "然后点\"停止\"再点\"开始自动对弈\"重新接管")
        else:
            self.expected_next = self._mover_by_counts(self.confirmed)
            self.log("将按当前轮次自动重试")

    # ---------- 其他 ----------
    def _save_image(self, img, tag):
        import cv2
        import os
        from ..infrastructure.storage.settings_store import app_data_dir
        d = os.path.join(str(app_data_dir()), "debug")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}.png")
        try:
            cv2.imwrite(path, img)
        except Exception:
            return None
        return path

    def _log_throttled(self, msg, key="throttle", gap=5.0):
        now = time.time()
        last = getattr(self, "_last_log_ts", {})
        if now - last.get(key, 0) > gap:
            last[key] = now
            self._last_log_ts = last
            self.log(msg)


# 兼容旧名（v1.0 的 auto_player.AutoPlayer）
AutoPlayer = AutoPlayService
