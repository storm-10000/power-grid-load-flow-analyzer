@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto use_launcher
python -B app.py
if errorlevel 1 goto failed
exit /b 0
:use_launcher
py -3 -B app.py
if not errorlevel 1 exit /b 0
:failed
echo.
echo Gridflow needs Python 3.10 or newer with Tkinter.
pause
exit /b 1
