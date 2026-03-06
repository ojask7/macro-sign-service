@echo off
REM Macro Sign Service - VBA Signing Helper
REM Usage: sign-vba.bat <file.xlsm> [pfx-file] [password]
REM
REM If no PFX file is specified, uses certs\default.pfx
REM If no PFX exists, generates one first using the Python CLI

setlocal

set FILE=%~1
set PFX_FILE=%~2
set PFX_PASSWORD=%~3

if "%FILE%"=="" (
    echo Usage: sign-vba.bat ^<file.xlsm^> [pfx-file] [password]
    echo.
    echo Examples:
    echo   sign-vba.bat report.xlsm
    echo   sign-vba.bat report.xlsm certs\custom.pfx
    echo   sign-vba.bat report.xlsm certs\custom.pfx mypassword
    exit /b 1
)

if not exist "%FILE%" (
    echo Error: File not found: %FILE%
    exit /b 1
)

REM Default PFX path
if "%PFX_FILE%"=="" set PFX_FILE=certs\default.pfx

REM Generate PFX if not found
if not exist "%PFX_FILE%" (
    echo No PFX certificate found. Generating...
    python -m cli.macro_sign_cli generate-pfx
    if errorlevel 1 (
        echo Error: Failed to generate certificate
        exit /b 1
    )
)

echo.
echo Signing %FILE% with %PFX_FILE%...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0sign-vba.ps1" -File "%FILE%" -PfxFile "%PFX_FILE%" -PfxPassword "%PFX_PASSWORD%"

exit /b %errorlevel%
