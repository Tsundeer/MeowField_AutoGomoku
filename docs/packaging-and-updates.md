# 打包与发布（MeowField_AutoGomoku）

## 便携版（zip）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-win-x64.ps1
```

步骤：读取 `src/meowfield_gomoku/__init__.py` 版本 -> 清理 `artifacts/` ->
PyInstaller onedir（含 assets 与 engines）-> 压缩为
`artifacts\publish\MeowField_AutoGomoku-{ver}-win-x64.zip`。

## 安装版（Inno Setup，可选）

安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 后：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-win-x64.ps1 -MakeInstaller
```

脚本自动定位 `ISCC.exe`，编译 `installer/MeowField_AutoGomoku.iss`，
产物：`artifacts\installer\MeowField_AutoGomoku-{ver}-win-x64-Setup.exe`。
安装器行为：默认安装到 `{autopf}`、可选桌面图标、安装前结束运行中的实例。

## GitHub Release

1. 提交并打 tag：`git tag v1.1.0 && git push --tags`
2. `gh release create v1.1.0 <zip> <setup.exe> --notes ...`
3. 应用内「检查更新」读取 `api.github.com/repos/Tsundeer/MeowField_AutoGomoku/releases/latest`
   比较语义化版本，提示新版本（不自动下载）。

## 冒烟清单（发布前）

- [ ] `python -m pytest tests/` 全绿
- [ ] 源码 `python main.py` 启动正常
- [ ] `dist` exe 启动：UI 渲染、窗口发现、引擎文件存在
- [ ] 版本号三处一致：`__init__.py` / README 头 / Release tag
