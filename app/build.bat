@echo off
rem AutoClick build. Hands over to tools\build (Python, stdlib only):
rem it creates .venv, installs deps + torch, downloads DINOv2 weights,
rem then runs PyInstaller. Output: app\dist\AutoClick\ (see README).
rem Keep this file ASCII only: cmd parses batch files with the OEM
rem codepage, non-ASCII lines get executed as garbage commands.
chcp 65001 >nul
cd /d "%~dp0.."
py -3 -c "pass" >nul 2>&1
if %errorlevel%==0 (
    py -3 tools\build %*
) else (
    python tools\build %*
)
set RC=%errorlevel%
echo.
if %RC%==0 (echo [build.bat] done) else (echo [build.bat] failed, see messages above)
pause
exit /b %RC%
