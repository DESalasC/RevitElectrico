@echo off
REM ============================================================================
REM  probar_agente.cmd - Prueba de humo de la cadena pyRevit -> Revit
REM
REM  1. Verifica que el agent host este escuchando.
REM  2. Ejecuta scripts\test_agent_simple.py dentro de Revit 2026.
REM
REM  Funciona desde cualquier carpeta (usa %~dp0, la ruta del propio .cmd).
REM
REM  Uso:
REM    D:\Work\PROJECTS\Actuales\T5-SantaMarta\scripts\probar_agente.cmd
REM ============================================================================

setlocal
set "AQUI=%~dp0"

echo [1/2] Estado del agent host
call "%AQUI%pyrevit.cmd" agent status
if errorlevel 1 (
    echo [ERROR] El CLI de pyRevit no pudo ejecutarse.
    exit /b 1
)

echo.
echo [2/2] Ejecutando test_agent_simple.py en Revit 2026
call "%AQUI%pyrevit.cmd" agent run "%AQUI%test_agent_simple.py" --revit=2026 --timeout 30
if errorlevel 1 (
    echo [ERROR] La ejecucion del script fallo.
    exit /b 1
)

echo.
echo Prueba completada.
exit /b 0
