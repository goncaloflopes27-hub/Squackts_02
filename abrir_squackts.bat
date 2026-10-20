@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%abrir_squackts.ps1"
set "SQUACKTS_EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %SQUACKTS_EXIT_CODE%
