@echo off
REM QueueCTL Installation Script for Windows

echo ============================================================
echo QueueCTL Installation Script
echo ============================================================
echo.

echo Step 1: Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Installing QueueCTL package...
pip install -e .
if errorlevel 1 (
    echo ERROR: Failed to install QueueCTL
    pause
    exit /b 1
)
echo.

echo Step 3: Verifying installation...
python verify_install.py
if errorlevel 1 (
    echo ERROR: Installation verification failed
    pause
    exit /b 1
)
echo.

echo ============================================================
echo Installation Complete!
echo ============================================================
echo.
echo You can now use QueueCTL:
echo   queuectl --help
echo   queuectl enqueue "{\"id\":\"test\",\"command\":\"echo Hello\"}"
echo.
echo Run quick_test.bat to test the system.
echo.
pause
