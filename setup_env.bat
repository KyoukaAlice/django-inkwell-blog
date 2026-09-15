@echo off
rem ============================================================================
rem  setup_env.bat - create the Python virtual environment and install packages
rem ============================================================================
rem
rem  Run this ONCE (or again whenever requirements.txt changes).
rem
rem  usage
rem  -----
rem      setup_env.bat              create .venv + install + initialise database
rem      setup_env.bat demo         same, and also load the demo data
rem      setup_env.bat sqlite       do everything against the local SQLite file
rem                                 (no MySQL needed)
rem      setup_env.bat sqlite demo  both
rem
rem  what it does
rem  ------------
rem      1. locate a supported Python (3.8 - 3.13)
rem      2. create the virtual environment in the .venv folder next to this file
rem      3. upgrade pip
rem      4. pip install -r requirements.txt
rem      5. run bootstrap.py: migrate, generate emoticons, optional demo data
rem
rem  notes
rem  -----
rem      * The virtual environment lives in .venv inside this folder. Delete that
rem        folder to start over. Nothing else on the machine is touched.
rem      * Database selection uses the DB_ENGINE environment variable:
rem          unset / mysql  ->  MySQL (settings.py keeps the original myblog_db)
rem          sqlite         ->  SQLite file db.sqlite3 next to manage.py
rem      * Keep this file CRLF-terminated and ASCII-only: cmd.exe misparses
rem        LF-only batch files (labels stop resolving) and needs ANSI text.
rem      * Delayed expansion is deliberately kept DISABLED so exclamation marks
rem        in printed text survive (for example the demo password BlogDemo!2026).
rem
rem ============================================================================

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DjangoBlog - environment setup

rem ---- work from this script's own folder, so it also works after a rename ----
cd /d "%~dp0"

rem ---- make sure the console can render UTF-8 output from Python --------------
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

rem ---- parse arguments -------------------------------------------------------
set "USE_SQLITE=0"
set "WITH_DEMO=0"
for %%A in (%*) do (
    if /I "%%~A"=="sqlite" set "USE_SQLITE=1"
    if /I "%%~A"=="demo" set "WITH_DEMO=1"
)
if "%USE_SQLITE%"=="1" set "DB_ENGINE=sqlite"

echo.
echo ============================================================
echo   DjangoBlog environment setup
echo ============================================================
if "%USE_SQLITE%"=="1" (
    echo   database : SQLite  ^(db.sqlite3^)
) else (
    echo   database : MySQL   ^(from settings.py, needs a running server^)
)
echo.

if not exist "manage.py" (
    echo [ERROR] manage.py not found in:
    echo         %CD%
    echo         Please keep this .bat file inside the DjangoBlog project folder.
    goto :fatal
)

rem ============================================================================
rem  1. locate a usable Python interpreter
rem
rem     Each candidate is tested in order. The first one that BOTH runs and is
rem     inside the supported 3.8 - 3.13 range wins, and the script then jumps
rem     forward. This avoids loops that would need delayed expansion, and avoids
rem     the "for /f over a quoted string" quoting trap.
rem ============================================================================
echo [1/5] locating Python...
set "BASE_PY="
set "BASE_PY_DESC="
set "PY_VERSION="

call :probe "py -3.9"
if defined BASE_PY goto :py_found
call :probe "py -3.13"
if defined BASE_PY goto :py_found
call :probe "py -3.12"
if defined BASE_PY goto :py_found
call :probe "py -3.11"
if defined BASE_PY goto :py_found
call :probe "py -3.10"
if defined BASE_PY goto :py_found
call :probe "py -3"
if defined BASE_PY goto :py_found
call :probe "python"
if defined BASE_PY goto :py_found
call :probe "D:\Python 3.9.10\python.exe"
if defined BASE_PY goto :py_found
call :probe "D:\Python 3.9\python.exe"
if defined BASE_PY goto :py_found
call :probe "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
if defined BASE_PY goto :py_found
call :probe "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if defined BASE_PY goto :py_found
call :probe "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined BASE_PY goto :py_found

echo.
echo [ERROR] No usable Python interpreter found.
echo         Install Python 3.8 - 3.13 from https://www.python.org/downloads/
echo         and tick "Add python.exe to PATH" during setup.
goto :fatal

:py_found
echo       found  %BASE_PY%  -  Python %PY_VERSION%

rem ============================================================================
rem  2. create the virtual environment
rem ============================================================================
echo.
echo [2/5] preparing virtual environment, folder .venv ...
if exist "%VENV_PY%" goto :venv_ready

if exist "%VENV_DIR%" (
    echo       removing an incomplete .venv from an earlier failed run...
    rmdir /s /q "%VENV_DIR%" >nul 2>&1
)
echo       creating .venv, this takes a few seconds...
%BASE_PY% -m venv "%VENV_DIR%"
if not exist "%VENV_PY%" (
    echo.
    echo [ERROR] python -m venv failed, or the result is incomplete:
    echo         %VENV_PY%
    echo         The official Windows installer includes venv, so this usually
    echo         means the Python installation is damaged.
    goto :fatal
)
echo       .venv created
goto :venv_done

:venv_ready
echo       reusing the existing .venv
echo       delete the .venv folder if you want a clean rebuild

:venv_done

rem ============================================================================
rem  3. upgrade pip
rem ============================================================================
echo.
echo [3/5] upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 goto :pip_upgrade_failed
echo       pip is up to date
goto :pip_done

:pip_upgrade_failed
echo       [warn] pip upgrade failed, continuing with the bundled version

:pip_done

rem ============================================================================
rem  4. install the project requirements
rem ============================================================================
echo.
echo [4/5] installing requirements...
echo       the first run downloads about 15 MB, please wait...
"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_install_failed
echo       requirements installed
goto :install_done

:pip_install_failed
echo.
echo [ERROR] pip install failed.
echo         If this is a network problem, use a faster mirror and retry:
echo             .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
goto :fatal

:install_done

rem ============================================================================
rem  5. initialise the database and static assets
rem ============================================================================
echo.
echo [5/5] initialising database and static assets...
set "BOOT_ARGS="
if "%WITH_DEMO%"=="1" set "BOOT_ARGS=--demo"
"%VENV_PY%" bootstrap.py %BOOT_ARGS%
if errorlevel 1 goto :fatal

echo.
echo ============================================================
echo   Setup finished
echo ============================================================
echo   start the site   :  start.bat            (MySQL)
echo                       start.bat sqlite     (SQLite, no MySQL)
echo   management cmd   :  manage.bat COMMAND
echo   demo accounts    :  demo / alice / bob
echo   demo password    :  BlogDemo!2026
echo.
pause
exit /b 0

rem ============================================================================
rem  Subroutine: test one candidate and, if it is usable, record it.
rem  Returns via "goto :eof" so the caller continues on the next line.
rem ============================================================================
:probe
set "PROBE_CMD=%~1"
set "PROBE_ARG="
if /I "%PROBE_CMD%"=="python" goto :probe_run
for /f "tokens=2,*" %%X in ("%PROBE_CMD%") do set "PROBE_ARG=%%X"

:probe_run
if defined PROBE_ARG (
    py %PROBE_ARG% -c "import sys; sys.exit(0 if sys.version_info[:2] in [(3,8),(3,9),(3,10),(3,11),(3,12),(3,13)] else 1)" >nul 2>&1
) else (
    "%PROBE_CMD%" -c "import sys; sys.exit(0 if sys.version_info[:2] in [(3,8),(3,9),(3,10),(3,11),(3,12),(3,13)] else 1)" >nul 2>&1
)
if errorlevel 1 goto :eof

if defined PROBE_ARG (
    for /f "delims=" %%V in ('py %PROBE_ARG% -c "import sys; print(sys.version.split()[0])"') do set "PY_VERSION=%%V"
) else (
    for /f "delims=" %%V in ('"%PROBE_CMD%" -c "import sys; print(sys.version.split()[0])"') do set "PY_VERSION=%%V"
)
set "BASE_PY=%PROBE_CMD%"
goto :eof

:fatal
echo.
echo ============================================================
echo   Setup did NOT finish - see the error above
echo ============================================================
echo.
pause
exit /b 1
