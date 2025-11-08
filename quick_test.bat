@echo off
REM Quick test script for Windows

echo Testing QueueCTL...
echo.

echo 1. Enqueuing test job...
python -m queuectl.cli enqueue "{\"id\":\"quick-test-1\",\"command\":\"echo Quick Test\"}"

echo.
echo 2. Starting worker...
python -m queuectl.cli worker start --count 1

echo.
echo 3. Waiting for job to complete...
timeout /t 3 /nobreak > nul

echo.
echo 4. Checking status...
python -m queuectl.cli status

echo.
echo 5. Listing jobs...
python -m queuectl.cli list

echo.
echo 6. Stopping workers...
python -m queuectl.cli worker stop

echo.
echo Test complete!
