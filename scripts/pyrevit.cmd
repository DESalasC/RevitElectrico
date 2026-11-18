@echo off
REM ============================================================================
REM  pyrevit.cmd - Lanzador de pyRevit con el runtime .NET correcto
REM
REM  Problema que resuelve:
REM    DOTNET_ROOT apunta a la copia embebida de AutoClaw, que no incluye
REM    Microsoft.WindowsDesktop.App. pyrevit.exe (WinForms) muere al arrancar
REM    con "You must install or update .NET".
REM
REM  Uso (desde cualquier carpeta):
REM    D:\Work\PROJECTS\Actuales\T5-SantaMarta\scripts\pyrevit.cmd agent status
REM    D:\Work\PROJECTS\Actuales\T5-SantaMarta\scripts\pyrevit.cmd agent run script.py --revit=2026
REM ============================================================================

setlocal

set "PYREVIT_EXE=C:\Users\Dario Salas\AppData\Roaming\pyRevit-Master\bin\pyrevit.exe"

REM Preferir el runtime de escritorio instalado a nivel de sistema
if exist "%ProgramFiles%\dotnet\shared\Microsoft.WindowsDesktop.App" (
    set "DOTNET_ROOT=%ProgramFiles%\dotnet"
)

if not exist "%PYREVIT_EXE%" (
    echo [pyrevit.cmd] No se encontro pyrevit.exe en "%PYREVIT_EXE%"
    exit /b 1
)

"%PYREVIT_EXE%" %*
exit /b %ERRORLEVEL%