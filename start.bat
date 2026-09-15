@echo off
rem ============================================================================
rem  start.bat - launch the DjangoBlog development server
rem ============================================================================
rem
rem  usage
rem  -----
rem      start.bat                 host 127.0.0.1 port 8000, MySQL from settings.py
rem      start.bat sqlite          use the local SQLite file instead of MySQL
rem      start.bat 8080            listen on port 8080
rem      start.bat sqlite 8080     SQLite on port 8080
rem      start.bat 0.0.0.0:8000    listen on every interface, for phone testing
rem
rem  notes
rem  -----
rem      * If .venv is missing, setup_env.bat runs automatically first.
rem      * DEBUG stays off by default. To get Django's detailed error pages while
rem        developing, open a cmd window and run:  set DJANGO_DEBUG=1  then this.
rem      * Press Ctrl+C in this window to stop the server.
rem
rem ============================================================================

setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title DjangoBlog - dev server

rem ---- work from this script's own folder -------------------------------------
cd /d "%~dp0"

rem ---- console must be able to render Python's UTF-8 output -------------------
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

rem ---- parse arguments: recognize sqlite, a bare port, or address:port ---------
set "USE_SQLITE=0"
set "ADDR=127.0.0.1:8000"
for %%A in (%*) do (
    if /I "%%~A"=="sqlite" (
        set "USE_SQLITE=1"
    ) else (
        echo %%~A| findstr /R /C:"^[0-9][0-9]*$" >nul && set "ADDR=127.0.0.1:%%~A"
        echo %%~A| findstr /R /C:"^[0-9][0-9.]*:[0-9][0-9]*$" >nul && set "ADDR=%%~A"
    )
)
if "%USE_SQLITE%"=="1" set "DB_ENGINE=sqlite"

echo.
echo ============================================================
echo   DjangoBlog
echo ============================================================
if "%USE_SQLITE%"=="1" (
    echo   database : SQLite  ^(db.sqlite3^)
) else (
    echo   database : MySQL   ^(settings.py: myblog_db^)
)
echo   address  : http://%ADDR%/
if defined DJANGO_DEBUG (
    echo   debug    : ON  ^(DJANGO_DEBUG=%DJANGO_DEBUG%^)
) else (
    echo   debug    : OFF ^(run "set DJANGO_DEBUG=1" to see detailed error pages^)
)
echo ============================================================
echo.

rem ---- 1. virtual environment -------------------------------------------------
if not exist "%VENV_PY%" (
    echo [1/2] .venv not found - running setup_env.bat first...
    echo.
    call "%~dp0setup_env.bat" %*
    if not exist "%VENV_PY%" (
        echo.
        echo [ERROR] environment setup did not finish, cannot start the server.
        pause
        exit /b 1
    )
) else (
    echo [1/2] virtual environment OK
)

rem ---- 2. sanity check --------------------------------------------------------
if not exist "manage.py" (
    echo [ERROR] manage.py not found in %CD%
    echo         Keep this .bat file inside the DjangoBlog project folder.
    pause
    exit /b 1
)

echo [2/2] starting server, watch this window for request logs
echo       press Ctrl+C to stop
echo.

rem ---- pre-flight: can we actually reach the database? ------------------------
rem Without this, a stopped MySQL server produces a 40-line Django traceback.
"%VENV_PY%" check_db.py
if !errorlevel! neq 0 (
    echo.
    echo ============================================================
    echo   Cannot reach the database - the server was NOT started
    echo ============================================================
    echo.
    echo   Option 1 - use SQLite instead, nothing else to install:
    echo       start.bat sqlite
    echo.
    echo   Option 2 - start MySQL, then run this script again.
    echo              Check the Windows service:
    echo                  sc query type= service state= all ^| findstr /I mysql
    echo.
    echo   Option 3 - if MySQL runs, verify the settings in
    echo              DjangoBlog\settings.py or set these variables:
    echo                  set DB_HOST=localhost
    echo                  set DB_PORT=3306
    echo                  set DB_USER=root
    echo                  set DB_PASSWORD=your-password
    echo.
    pause
    exit /b 1
)

echo ------------------------------------------------------------
echo   open this in your browser:  http://%ADDR%/
echo ------------------------------------------------------------
echo.

rem ---- run it ------------------------------------------------------------------
rem NOTE: do NOT wrap this call in a parenthesised block. Parentheses break
rem       paths that contain spaces, for example "C:\Program Files\...\".
"%VENV_PY%" manage.py runserver %ADDR%

set "EXIT_CODE=%errorlevel%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo ============================================================
    echo   The server exited with code %EXIT_CODE%
    echo ============================================================
    echo.
    echo   Common causes:
    echo     * MySQL is not running          - try   start.bat sqlite
    echo     * port %ADDR% is already in use - try   start.bat 8001
    echo     * migrations were never applied - run   setup_env.bat
    echo     * a dependency is missing       - run   setup_env.bat
    echo.
) else (
    echo server stopped.
)
pause
exit /b %EXIT_CODE%
