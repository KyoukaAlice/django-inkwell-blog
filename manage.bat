@echo off
rem ============================================================================
rem  manage.bat - run any "python manage.py ..." command inside the venv
rem ============================================================================
rem
rem  usage
rem  -----
rem      manage.bat                              list every available command
rem      manage.bat help COMMAND                 detailed help for one command
rem      manage.bat migrate                      apply database migrations
rem      manage.bat makemigrations blog          create migrations after model edits
rem      manage.bat createsuperuser              create an admin account
rem      manage.bat seed_demo                    load the demo data
rem      manage.bat seed_demo --reset            wipe blog data, then load demo data
rem      manage.bat generate_emoticons           regenerate the comment emoji SVGs
rem      manage.bat rerender_posts               rebuild the cached Markdown HTML
rem      manage.bat shell                        interactive Python shell
rem      manage.bat test blog                    run the unit tests
rem      manage.bat test blog -v 2               run them verbosely
rem      manage.bat collectstatic --noinput      gather static files for deployment
rem
rem      Put "sqlite" first to run a command against SQLite instead of MySQL:
rem          manage.bat sqlite migrate
rem
rem  limitations
rem  -----------
rem      Arguments containing round brackets are NOT supported: cmd.exe parses
rem      brackets inside a wrapper variable and aborts with
rem      ") was unexpected at this time". For those, call manage.py directly:
rem          .venv\Scripts\python.exe manage.py shell -c "print(42)"
rem
rem      Keep this file CRLF-terminated: cmd.exe misparses LF-only batch files.
rem
rem ============================================================================

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DjangoBlog - manage.py

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo.
    echo [ERROR] virtual environment not found:
    echo         %VENV_PY%
    echo.
    echo         Run setup_env.bat first.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo.
    echo No command given - showing the built-in command list instead.
    echo.
    "%VENV_PY%" manage.py help
    echo.
    echo ============================================================
    echo   Tip: manage.bat help COMMAND   for details on one command
    echo ============================================================
    pause
    exit /b 0
)

rem ---- an optional leading "sqlite" switches the database for this run --------
if /I "%~1"=="sqlite" goto :use_sqlite

"%VENV_PY%" manage.py %*
set "EXIT_CODE=%errorlevel%"
goto :report

:use_sqlite
set "DB_ENGINE=sqlite"
echo [db] using SQLite
rem shift does not update %*, so the remaining arguments are collected by hand.
rem Only the FIRST argument is dropped, and later arguments are passed through
rem unquoted-but-rejoined, which is fine for the commands this wrapper supports.
set "REST="
set "SKIP=1"
for %%A in (%*) do (
    if defined SKIP (
        set "SKIP="
    ) else (
        call :append %%A
    )
)
"%VENV_PY%" manage.py %REST%
set "EXIT_CODE=%errorlevel%"
goto :report

:append
set "REST=%REST% %*"
goto :eof

:report
echo.
if not "%EXIT_CODE%"=="0" (
    echo [exit code %EXIT_CODE%]
    echo.
    echo   If the command failed to connect to the database, try:
    echo       manage.bat sqlite COMMAND
) else (
    echo [done]
)
pause
exit /b %EXIT_CODE%
