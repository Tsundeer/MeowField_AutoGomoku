# MeowField_AutoGomoku 架构说明

本文描述 v1.1.0 重构后的项目结构。设计范式对齐 MeowField_AutoPiano
（分层 + 组合根 + 基础设施隔离），实现语言为 Python（视觉/自动化生态成熟）。

## 分层与依赖方向

```
ui ──────────────┐
                 ▼
application ──► domain
                 ▲
infrastructure ──┘（实现 application 契约）
```

依赖只允许自上而下；`domain` 不依赖任何其他层，`application` 通过
`contracts.py` 中的接口（IBoardDetector / IMoveEngine / IWindowController）
依赖倒置，具体实现全部位于 `infrastructure`，由组合根装配。

## 目录布局

```
├── pyproject.toml            # 项目元数据；版本单点 = src/meowfield_gomoku/__init__.py
├── main.py                   # 兼容入口（转发到包）
├── 一键启动.bat               # 用户启动脚本（找 Python、装依赖、启动）
├── src/meowfield_gomoku/
│   ├── __init__.py           # __version__（唯一版本来源）
│   ├── app.py                # 组合根：日志、异常钩子、服务装配、入口
│   ├── config.py             # 应用常量（识别阈值、轮询间隔、引擎预算）
│   ├── domain/               # 纯逻辑：棋盘模型、坐标、轮次判定
│   │   └── board.py
│   ├── application/          # 用例编排
│   │   ├── contracts.py      # 服务接口 + Detection/异常
│   │   └── auto_play_service.py   # 自动对弈状态机（后台线程）
│   ├── infrastructure/       # 技术实现
│   │   ├── vision/detector.py     # OpenCV 棋盘识别（面板/网格/落子分类）
│   │   ├── capture/windows.py     # 窗口查找、PrintWindow/mss 截屏、SendInput
│   │   ├── engine/simple_engine.py# 内置纯 Python 引擎（α-β）
│   │   ├── engine/ai_factory.py   # Rapfi 子进程（Gomocup 协议）+ 引擎选择
│   │   └── storage/               # 设置存储（原子写+备份）、日志装配
│   └── ui/main_window.py     # CustomTkinter 主窗口
├── tests/                    # pytest，目录镜像分层
│   ├── application/          # 状态机场景（17 项断言）
│   └── infrastructure/       # 识别回归 / 内置引擎 / Rapfi 协议
├── tools/                    # 开发工具（calibrate 标定、make_icon 图标）
├── docs/                     # ARCHITECTURE / ACCEPTANCE / packaging-and-updates
├── assets/                   # 图标等资源
├── samples/                  # 识别标定样本
├── installer/                # Inno Setup 6 脚本
└── scripts/                  # build-win-x64.ps1（打包 + 压缩 + 可选安装器）
```

## 组合根（app.py）

1. `setup_logging()`：`%LocalAppData%\MeowField_AutoGomoku\logs\app.log`
   按日滚动，保留 14 份；UI 日志面板经 QueueLogHandler 桥接。
2. `sys.excepthook`：未处理异常 -> 日志 + 弹窗（不无声崩溃）。
3. `build_services()`：读取用户设置 -> 装配 IWindowController（Windows 实现）、
   BoardDetector、AutoPlayService（注入 engine_factory 实现依赖倒置）。
4. `run_ui()`：主窗口接收注入的服务；退出时停线程、停引擎、flush 日志。

## 配置管理

- **应用常量**（代码内，`config.py`）：识别阈值、轮询间隔、引擎时间预算。
- **用户设置**（`%LocalAppData%\MeowField_AutoGomoku\settings.json`）：
  执色、引擎、线程数、落子停顿。原子写入（临时文件 -> fsync -> replace），
  保留 `.bak` 备份；带 `schema_version`。v1.0 的项目根 `config.json`
  会在首次读取时自动迁移。
- **Rapfi 引擎配置**（`engines/config.toml`）：线程数由程序在启动引擎前写入。

## 版本与发布

- 版本单点：`src/meowfield_gomoku/__init__.py` 的 `__version__`，
  pyproject 动态读取；git tag `v1.1.0` 风格。
- `scripts/build-win-x64.ps1`：读版本 -> PyInstaller onedir -> zip ->
  （可选）Inno Setup 编译安装器。产物在 `artifacts/`。
- GitHub Release 附加 zip（便携版）与 Setup.exe（安装版）。

## 质量门

- `python -m pytest tests/`：全部通过（Rapfi 协议测试需引擎在场，
  缺失时自动 skip）。
- `python main.py` 冒烟：窗口出现、日志无 Critical。
- 打包产物冒烟：exe 启动、UI 渲染、引擎文件齐全。
