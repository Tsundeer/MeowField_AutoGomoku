# -*- coding: utf-8 -*-
"""全局配置（可通过 GUI / config.json 覆盖）。"""

# 游戏窗口
WINDOW_TITLE_KEYWORDS = ["开放空间"]
WINDOW_PROCESS_HINTS = ["launcher.exe"]

# 棋盘
BOARD_N = 13            # 13x13，列 A-M，行 1-13

# 自动对弈
POLL_INTERVAL = 0.55        # 截图轮询间隔（秒）
STABLE_READS = 2            # 连续相同读取次数才认定状态稳定
CLICK_TIMEOUT = 3.0         # 点击后等待我方棋子出现的超时（秒）
CLICK_RETRIES = 2           # 点击未生效的重试次数
CLICK_HOLD = 0.09           # 鼠标按下持续时间（秒）
VERIFY_HOVER_DELAY = 0.35   # 落子前把鼠标移到目标点后等待幻影消失的时间（秒）

# 引擎
ENGINE_TIME_LIMIT = None     # None = 不人为限制（引擎按 RAPFI_TURN_TIME_MS 预算自由思考）
RAPFI_TURN_TIME_MS = 20000   # Rapfi 每步思考预算（毫秒）。找到必胜会提前落子；
                             # 均势局面会走满预算换取棋力。想要更快改小即可。
ENGINE_THREADS = 0           # 引擎线程数。0 = 用满全部逻辑核（推荐）；
                             # 也可设为物理核数（如 14），留出超线程余量给系统。

# ---- 识别阈值（针对"开放空间"默认棋盘皮肤标定，一般无需改动）----
# 面板底色 HSV 范围（米色大面板）
PANEL_H = (8, 35)
PANEL_S = (15, 100)
PANEL_V = (195, 256)

# 网格线颜色（蓝色通道范围，BGR 下 B≈210，格子 B≈221）
LINE_B = (200, 216)
LINE_B_RELAX = (175, 220)   # 外推边缘线时放宽

# 石子分类（基于交叉点采样块的中位 HSV）
STONE_DARK_V = 150          # V 低于此值 -> 黑子
STONE_WHITE_S = 16          # S 低于此值且 V 在白子区间 -> 白子
STONE_WHITE_V = (155, 236)
EMPTY_S_MIN = 18            # 空点的 S 下限（米色底）
EMPTY_V_MIN = 228           # 空点的 V 下限
