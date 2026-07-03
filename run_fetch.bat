@echo off
setlocal

wsl bash -lc "cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main && { PYTHON=.venv/bin/python; [ -x $PYTHON ] || PYTHON=python3; STAMP=$(TZ=Asia/Taipei date +%%Y%%m%%d); TARGET=$(TZ=Asia/Taipei date +%%Y-%%m-%%d); $PYTHON scripts/run/run_ncf_daily_pipeline.py --date-stamp $STAMP --refresh-target-date $TARGET --ohlcv-target-date $TARGET --only-refresh --force-refresh --strict-refresh --fail-on-ohlcv-warning; }"

if %ERRORLEVEL% EQU 0 (
    echo Fetch SUCCESS
) else (
    echo Fetch FAILED
)

exit /b %ERRORLEVEL%
