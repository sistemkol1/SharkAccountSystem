@echo off
chcp 1251 >nul
title Shark Account System - Builder

echo.
echo ===================================================
echo      SHARK ACCOUNT SYSTEM - BUILDER
echo      PyInstaller + Inno Setup
echo ===================================================
echo.

echo [CHECK] Proverjaem zavisimosti...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [OSHIBKA] Python ne najden!
    echo          Skachaj: https://python.org/downloads
    pause
    exit /b 1
)
python --version

pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ustanavlivaem PyInstaller...
    pip install pyinstaller --quiet
)
echo [OK] PyInstaller gotov

if not exist "node\node.exe" (
    echo.
    echo [OSHIBKA] Portable Node.js ne najden!
    echo          1. Zajdi na https://nodejs.org/dist/latest/
    echo          2. Skachaj node-vXX-win-x64.zip
    echo          3. Voz'mi tol'ko node.exe
    echo          4. Polozhi v papku node\node.exe
    echo.
    pause
    exit /b 1
)
echo [OK] node\node.exe najden

set "INNO="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "INNO=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set "INNO=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set "INNO=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
if exist "C:\Program Files\Inno Setup 5\ISCC.exe"       set "INNO=C:\Program Files\Inno Setup 5\ISCC.exe"

if not defined INNO (
    echo.
    echo [OSHIBKA] Inno Setup ne najden!
    echo          Skachaj besplatno: https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)
echo [OK] Inno Setup najden: %INNO%

echo.
echo Vse zavisimosti OK. Nachinaem sborku...
echo.

echo [1/4] Ochishchaem starye artefakty...
if exist "dist\SharkAccountSystem" rmdir /s /q "dist\SharkAccountSystem"
if exist "build"                   rmdir /s /q "build"
if exist "installer_output"        rmdir /s /q "installer_output"
echo      Gotovo.

echo.
echo [2/4] Sobiraem EXE cherez PyInstaller (1-3 min)...
echo.

set "ICON_FLAG="
if exist "icon.ico" set "ICON_FLAG=--icon icon.ico"

python -m PyInstaller --noconfirm --onedir --windowed --name "SharkAccountSystem" %ICON_FLAG% --add-data "session_bridge.js;." --add-data "subsitems.js;." --add-data "config.json;." --hidden-import flet --hidden-import flet_core --hidden-import flet_runtime --collect-all flet --collect-all flet_core main.py >pyinstaller_log.txt 2>&1

if errorlevel 1 (
    echo [OSHIBKA] PyInstaller upal! Log: pyinstaller_log.txt
    type pyinstaller_log.txt | findstr /i "error\|traceback" | more
    pause
    exit /b 1
)
echo [OK] EXE sobran

echo.
echo [3/4] Podgotavlivaem dist\...

set "DIST=dist\SharkAccountSystem"

if not exist "%DIST%\sessions"    mkdir "%DIST%\sessions"
if not exist "%DIST%\avatars"     mkdir "%DIST%\avatars"
if not exist "%DIST%\mafs"        mkdir "%DIST%\mafs"
if not exist "%DIST%\node"        mkdir "%DIST%\node"

copy /y "node\node.exe" "%DIST%\node\node.exe" >nul
echo      [OK] node.exe skopirovan

if exist "node_modules" (
    echo      Kopèðóåì node_modules...
    xcopy /e /i /q /y "node_modules" "%DIST%\node_modules" >nul
    echo      [OK] node_modules skopirovan
) else (
    echo      [WARN] node_modules ne najden - zapusti: npm install
)

if exist "resources"  xcopy /e /i /q /y "resources"  "%DIST%\resources"  >nul
if exist "bg.jpg"     copy /y "bg.jpg"    "%DIST%\bg.jpg"   >nul
if exist "icon.ico"   copy /y "icon.ico"  "%DIST%\icon.ico" >nul

echo      [OK] Fajly gotovy

echo.
echo [4/4] Sobiraem ustanovshchik cherez Inno Setup...

if not exist "installer_output" mkdir "installer_output"

"%INNO%" "installer.iss"

if errorlevel 1 (
    echo [OSHIBKA] Inno Setup upal! Prover' installer.iss
    pause
    exit /b 1
)

if exist "pyinstaller_log.txt" del "pyinstaller_log.txt"

echo.
echo ===================================================
echo  SBORKA ZAVERSHENA!
echo ===================================================
echo.
for %%f in (installer_output\*.exe) do echo  Ustanovshchik: %%f
echo.

explorer "installer_output"
pause
