@echo off
echo ============================================
echo MT5 EA Installation Checker
echo ============================================
echo.

set MT5_PATH=C:\Users\Lenovo\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts

echo Checking if MT5 Experts folder exists...
if exist "%MT5_PATH%" (
    echo [OK] Experts folder found: %MT5_PATH%
    echo.
    echo Listing files in Experts folder:
    dir "%MT5_PATH%\*.mq5" /b
    echo.
    echo Checking for EMA_Crossover_Strategy.mq5...
    if exist "%MT5_PATH%\EMA_Crossover_Strategy.mq5" (
        echo [OK] EMA_Crossover_Strategy.mq5 found!
        echo.
        echo File details:
        dir "%MT5_PATH%\EMA_Crossover_Strategy.mq5"
    ) else (
        echo [ERROR] EMA_Crossover_Strategy.mq5 NOT found in Experts folder!
        echo.
        echo Please copy the file to: %MT5_PATH%
    )
) else (
    echo [ERROR] MT5 Experts folder not found!
    echo Expected path: %MT5_PATH%
    echo.
    echo Please verify your MT5 installation path.
)

echo.
echo ============================================
pause
