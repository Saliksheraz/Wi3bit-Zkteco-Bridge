@echo off
setlocal

echo Resetting repository to HEAD...
python\python.exe manage.py runserver
if %ERRORLEVEL% neq 0 (
    echo ERROR: django server failed to  run!
    pause
    exit /b
)

echo Repository updated successfully!
pause
