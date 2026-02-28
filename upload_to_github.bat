@echo off
setlocal

set REPO_URL=https://github.com/sistemkol1/SharkAccountSystem.git
set BRANCH=main

echo.
echo === SharkAccountSystem - GitHub Upload ===
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git not found. Install: https://git-scm.com/
    pause & exit /b 1
)

if not exist ".git" (
    echo [1/6] Git init...
    git init
    git branch -M %BRANCH%
) else (
    echo [1/6] Git already exists - skip
)

echo [2/6] Checking .gitignore...
if not exist ".gitignore" (
    echo [ERROR] .gitignore not found. Put it in project folder first.
    pause & exit /b 1
)

echo [3/6] Setting remote origin...
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    git remote add origin %REPO_URL%
) else (
    git remote set-url origin %REPO_URL%
)
echo     Remote: %REPO_URL%

echo [4/6] Adding files...
git add .

git rm --cached data.db              >nul 2>&1
git rm --cached accs.txt             >nul 2>&1
git rm --cached config.json          >nul 2>&1
git rm --cached items_success.txt    >nul 2>&1
git rm --cached subs_success.txt     >nul 2>&1
git rm --cached subs_blacklist.txt   >nul 2>&1
git rm -r --cached node_modules/     >nul 2>&1
git rm -r --cached __pycache__/      >nul 2>&1
git rm -r --cached mafs/             >nul 2>&1
git rm -r --cached avatars/          >nul 2>&1
git rm -r --cached build/            >nul 2>&1
git rm -r --cached dist/             >nul 2>&1
git rm -r --cached installer_output/ >nul 2>&1

echo.
echo --- Files to commit ---
git status --short
echo -----------------------
echo.

echo [5/6] Commit...
set COMMIT_MSG=Initial commit
set /p COMMIT_MSG="Commit message (Enter = Initial commit): "
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Initial commit

git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo [!] Nothing to commit or error.
    pause & exit /b 1
)

echo [6/6] Pushing to GitHub...
git push -u origin %BRANCH%

if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Possible reasons:
    echo   1. Repository not created on github.com yet
    echo   2. Wrong REPO_URL in this script
    echo   3. Auth failed - check your token
    echo.
    echo Create repo here: https://github.com/new
) else (
    echo.
    echo SUCCESS! Uploaded to GitHub:
    echo %REPO_URL%
)

echo.
pause
