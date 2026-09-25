# v1.1.0 架构重构验收记录（2026-09-25）

对照 MeowField_AutoPiano 的架构范式重构为标准 Python 桌面应用结构。

## 已验证

- [x] 分层结构：src/meowfield_gomoku/{domain, application, infrastructure, ui}，
      依赖方向 ui→application→domain，infrastructure 实现契约（contracts.py）
- [x] 组合根 app.py：日志初始化 → 异常钩子 → build_services() → run_ui()
- [x] 用户设置迁移至 %LocalAppData%\MeowField_AutoGomoku\settings.json，
      原子写入 + .bak 备份 + schema_version；自动兼容读取 v1.0 根目录 config.json
- [x] 文件日志 %LocalAppData%\MeowField_AutoGomoku\logs\app.log 按日滚动保留 14 份
- [x] 版本单点 __init__.__version__=1.1.0，pyproject 动态读取，pip install -e . 可用
- [x] pytest 化：tests/ 镜像分层（application 状态机 17 断言 /
      infrastructure 识别回归 / 内置引擎 / Rapfi 协议，引擎缺失自动 skip）
- [x] UI 视觉零改动（CustomTkinter 深色界面 + 棋盘 + 设置），新增版本角标与「检查更新」
- [x] find_game_window 排除本程序自身进程（标题同样含"开放空间"导致误匹配的缺陷）
- [x] engines/ 定位兼容：源码=仓库根；打包=PyInstaller 解包目录（sys._MEIPASS）
- [x] 更新检查：GitHub releases/latest 语义化版本比较（不自动下载）

## 冒烟

- python main.py：窗口出现、日志面板滚动、无 Critical
- pytest tests/：2 passed + rapfi 协议 1 passed（有引擎时）
- 打包：scripts/build-win-x64.ps1 → 便携 zip（+ 可选 Inno Setup 安装器）

## 已知边界

- 内置引擎不限时模式在均势局面搜索不可控，统一走 20s/步预算（RAPFI_TURN_TIME_MS）
- 截屏对独占全屏不可用，需窗口化（与 v1.0 一致）

## v1.1.1 增量验收（2026-09-26）

- [x] 检查更新重写：API(ETag 条件请求，304 不计限额) -> releases.atom -> HTML 页面
      三级降级 + 本地缓存 1 小时；实测 API 200 拿到 v1.1.0、缓存命中、ETag 生效
- [x] 线程数动态提示：0 = 用满全部逻辑核（显示本机 N 逻辑核），随设置即时更新
- [x] 启动自动申请管理员（ShellExecute runas）；用户取消 UAC 则降级继续并写警告日志
      （实测降级路径：UI 正常、日志含"未获得管理员权限…"警告）
      —— 原因：游戏常以管理员运行，普通权限进程的 SendInput 被 UIPI 拦截导致无法点击
- [x] Inno Setup 6 安装并加入用户 PATH；scripts/build-win-x64.ps1 产出
      便携 zip + 安装版 Setup.exe（MeowField_AutoGomoku-{ver}-win-x64-Setup.exe）

## v1.1.2 增量验收（2026-09-26）

- [x] 深浅色主题：设置区右上「深色/浅色/系统」分段切换，随持久化恢复；
      全部界面颜色改为 (浅色, 深色) 双值随主题自动切换，棋盘木色两种主题下不变
- [x] 思考上限回归：设置项「思考上限(秒)」默认 20（5~120 可选），
      链路 UI -> AutoPlayService.think_limit -> Rapfi best_move 每步下发
      INFO timeout_turn（运行时改预算无需重启引擎）；simple 引擎同链路生效
- [x] 窗口匹配再收紧：兜底排除 python/pythonw/本程序 exe 名，
      提权重启等场景不再短暂误匹配自身实例（实测日志显示明确拒绝原因）
- [x] pytest 全绿；exe 打包冒烟通过
