@echo off
rem 打包 MeowField 自动五子棋为 exe（onedir）
cd /d "%~dp0.."
pip install --quiet -r requirements.txt pyinstaller
python tools/make_icon.py
pyinstaller --noconfirm --clean --windowed --icon assets/icon.ico ^
  --name MeowField_AutoGomoku ^
  --collect-all customtkinter ^
  --add-data "assets;assets" ^
  --add-data "engines;engines" ^
  main.py
if errorlevel 1 (echo BUILD FAILED & exit /b 1)
powershell -NoProfile -Command "Compress-Archive -Path 'dist\MeowField_AutoGomoku\*' -DestinationPath 'dist\MeowField_AutoGomoku_win64.zip' -Force"
echo DONE: dist\MeowField_AutoGomoku_win64.zip
