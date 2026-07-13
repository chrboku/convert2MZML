@echo off
setlocal enabledelayedexpansion

REM Install uv if not available
where uv >nul 2>nul
if not errorlevel 1 goto :uv_found

echo uv is not installed.

REM ask user if they want to install uv
set /p install_uv=Do you want to install uv? (y/n): 
if /i "!install_uv!" neq "y" (
    echo uv is required to run this script. Exiting.
    pause
    exit /b 0
)

REM install uv using powershell
echo Installing uv...
powershell.exe -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

REM ask user to restart the terminal
echo Please restart the terminal and run this script again. If you double-clicked this script, please close and re-open it. Exiting.
pause
exit /b 0

:uv_found

uv run convert2raw
pause