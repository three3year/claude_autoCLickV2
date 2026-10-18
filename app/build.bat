@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem AutoClick 打包 (onedir + --uac-admin; 詳見 AutoClick.spec 與 app/CLAUDE.md)
rem 產物: app\dist\AutoClick\ — 整個資料夾即可攜交付物 (免 Python 免網路)

set PY=..\.venv\Scripts\python
%PY% -m pip show pyinstaller >nul 2>&1 || %PY% -m pip install -q pyinstaller

echo [AutoClick] 打包中 (torch + DINOv2 隨包, 需要幾分鐘)...
%PY% -m PyInstaller --noconfirm AutoClick.spec
if not exist dist\AutoClick\AutoClick.exe (
    echo 打包失敗, 請檢查上方錯誤訊息
    exit /b 1
)

rem 打包版資料夾裡沒有使用者資料 (ADR 0015、0017): 流程資料夾在 repo 的 flows\
rem (exe 往上找不到 repo 時 %USERPROFILE%\AutoClick\),
rem 本機狀態與日誌在 %LOCALAPPDATA%\AutoClick\ ; 不必放任何東西到 exe 旁。

echo.
echo 完成! 交付物: %~dp0dist\AutoClick\  (執行 AutoClick.exe, 開啟時跳 UAC)
echo 部署到既有機器 = 整個 AutoClick\ 資料夾換掉
