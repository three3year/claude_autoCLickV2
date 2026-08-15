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

echo [AutoClick] 放入 arknights profile (只在不存在時複製, 絕不覆蓋使用者資料)...
if not exist dist\AutoClick\profiles\arknights (
    robocopy ..\profiles\arknights\templates dist\AutoClick\profiles\arknights\templates /E /NFL /NDL /NJH /NJS >nul
    robocopy ..\profiles\arknights\registered dist\AutoClick\profiles\arknights\registered /E /NFL /NDL /NJH /NJS >nul
    copy /y ..\profiles\arknights\config.yaml dist\AutoClick\profiles\arknights\ >nul
)

echo.
echo 完成! 交付物: %~dp0dist\AutoClick\  (執行 AutoClick.exe, 開啟時跳 UAC)
echo 部署到既有機器 = 只覆蓋 AutoClick*.exe 與 _internal\ , 不動 profiles\
