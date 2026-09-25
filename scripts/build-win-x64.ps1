# MeowField_AutoGomoku 打包脚本（镜像 AutoPiano publish-win-x64.ps1 流程）
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\build-win-x64.ps1 [-SkipInstaller]
# 产物：
#   artifacts\publish\MeowField_AutoGomoku-{ver}-win-x64.zip        便携版
#   artifacts\installer\MeowField_AutoGomoku-{ver}-win-x64-Setup.exe 安装版（可选）

param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# ---- 版本单点：src/meowfield_gomoku/__init__.py ----
$initFile = Join-Path $repoRoot "src\meowfield_gomoku\__init__.py"
$initText = Get-Content $initFile -Raw -Encoding UTF8
if ($initText -notmatch '__version__\s*=\s*"(\d+\.\d+\.\d+)"') {
    throw "无法从 $initFile 读取版本号"
}
$version = $Matches[1]
Write-Host "== MeowField_AutoGomoku v$version ==" -ForegroundColor Cyan

# ---- 清理 ----
$artifacts = Join-Path $repoRoot "artifacts"
if (Test-Path $artifacts) { Remove-Item $artifacts -Recurse -Force }
Remove-Item (Join-Path $repoRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $repoRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue

# ---- PyInstaller ----
$spec = Join-Path $repoRoot "installer\MeowField_AutoGomoku.spec"
if (Test-Path $spec) { Remove-Item $spec -Force }
python -m PyInstaller --noconfirm --clean --windowed --icon assets\icon.ico `
    --name MeowField_AutoGomoku `
    --workpath build --distpath dist `
    --collect-all customtkinter `
    --add-data "assets;assets" `
    --add-data "engines;engines" `
    main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

# ---- 目录整理 ----
$publishDir = Join-Path $repoRoot "dist\MeowField_AutoGomoku"
if (-not (Test-Path $publishDir)) { throw "未找到 PyInstaller 输出：$publishDir" }

# ---- 压缩便携版 ----
$publishArt = Join-Path $artifacts "publish"
New-Item -ItemType Directory -Force -Path $publishArt | Out-Null
$zipPath = Join-Path $publishArt "MeowField_AutoGomoku-$version-win-x64.zip"
Compress-Archive -Path "$publishDir\*" -DestinationPath $zipPath -Force
Write-Host "便携版: $zipPath" -ForegroundColor Green

# ---- 安装器（可选）----
if (-not $SkipInstaller) {
    $isccCandidates = @(@(
        (Get-Command iscc -ErrorAction SilentlyContinue).Source,
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) })
    if ($isccCandidates.Count -gt 0) {
        $iscc = $isccCandidates[0]
        & $iscc "/DMyAppVersion=$version" "/DPublishDir=$publishDir" `
            (Join-Path $repoRoot "installer\MeowField_AutoGomoku.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败" }
        Write-Host "安装版: artifacts\installer\" -ForegroundColor Green
    }
    else {
        Write-Warning "未找到 Inno Setup 6，跳过安装器（可安装后重跑 -SkipInstaller:$false）"
    }
}

Write-Host "== 完成 v$version ==" -ForegroundColor Cyan
