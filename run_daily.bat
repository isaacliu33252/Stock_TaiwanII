@echo off
setlocal

wsl bash -lc "cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main && { PYTHON=.venv/bin/python; [ -x $PYTHON ] || PYTHON=python3; STAMP=$(TZ=Asia/Taipei date +%%Y%%m%%d); TARGET=$(TZ=Asia/Taipei date +%%Y-%%m-%%d); $PYTHON scripts/run/run_ncf_daily_pipeline.py --date-stamp $STAMP --ohlcv-target-date $TARGET --skip-refresh --refresh-external-cache; }"

if %ERRORLEVEL% EQU 0 (
    echo Pipeline SUCCESS
) else (
    echo Pipeline FAILED
)

exit /b %ERRORLEVEL%
