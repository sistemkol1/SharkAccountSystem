@echo off
setlocal

echo.
echo === SharkAccountSystem - Install Dependencies ===
echo.

:: ── Check Python ──────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Install: https://www.python.org/downloads/
    pause & exit /b 1
)
python --version

:: ── Check Node.js ─────────────────────────────────
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found.
    echo Install: https://nodejs.org/
    pause & exit /b 1
)
node --version

echo.
echo [1/4] Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)

echo.
echo [2/4] Installing Playwright browser...
playwright install chromium
if errorlevel 1 (
    python -m playwright install chromium
)

echo.
echo [3/4] Installing Node.js packages...
npm install
if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause & exit /b 1
)

echo.
echo [4/4] Installing cheerio (required for badges)...
npm install cheerio
if errorlevel 1 (
    echo [ERROR] cheerio install failed.
    pause & exit /b 1
)

echo.
echo ================================
echo All dependencies installed!
echo Run the app: python main.py
echo ================================
echo.
pause
