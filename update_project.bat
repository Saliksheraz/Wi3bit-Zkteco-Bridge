@echo off
setlocal

echo Resetting repository to HEAD...
PortableGit\bin\git.exe reset --hard HEAD
if %ERRORLEVEL% neq 0 (
    echo ERROR: git reset failed!
    pause
    exit /b
)

echo Pulling latest changes...
PortableGit\bin\git.exe pull
if %ERRORLEVEL% neq 0 (
    echo ERROR: git pull failed!
    pause
    exit /b
)

echo Repository updated successfully!
pause
