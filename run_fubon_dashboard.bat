@echo off
setlocal

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL is required to run this project command.
  echo Please open WSL and run: ./run_fubon_dashboard.sh
  pause
  exit /b 1
)

for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%~dp0"`) do set "WSL_PROJECT_DIR=%%I"

echo.
echo Group A+ Fubon read-only dashboard refresh
echo.
echo This will ask for:
echo   1. Fubon login password
echo   2. Fubon certificate password
echo.
echo When typing passwords, the screen will not show letters or stars.
echo Type the password and press Enter.
echo.
echo It only reads holdings and cash. It does not place orders.
echo.

wsl.exe -e bash -lc "cd '%WSL_PROJECT_DIR%' && .venv/bin/python -m group_a_plus.dashboard.update_dashboard --refresh-fubon --local-config-dir 'C:\fubon' --json; rc=$?; echo; if [ $rc -eq 0 ]; then echo 'Dashboard: data/private/group_a_plus_dashboard.html'; else echo 'Refresh failed. See message above.'; fi; echo; read -r -p 'Press Enter to close...' _; exit $rc"

exit /b %ERRORLEVEL%
