@echo off
setlocal
cd /d "%~dp0"
title VortexCore Hub Launcher

:: Verificar privilegios de administrador y auto-elevar si es necesario
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [VortexCore Hub] Solicitando permisos de Administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"\"%~dp0Iniciar VortexCore.bat\"\"' -Verb RunAs"
    exit /b
)

:: Detectar ejecutable de Python silencioso (pythonw.exe)
set "PYTHON_EXE="
if exist "D:\Programacion\laragon\bin\python\python-3.13\pythonw.exe" (
    set "PYTHON_EXE=D:\Programacion\laragon\bin\python\python-3.13\pythonw.exe"
) else (
    where pythonw >nul 2>&1 && for /f "delims=" %%i in ('where pythonw') do set "PYTHON_EXE=%%i"
    if not defined PYTHON_EXE (
        where python >nul 2>&1 && for /f "delims=" %%i in ('where python') do set "PYTHON_EXE=%%i"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] No se encontro Python en el sistema.
    pause
    exit /b
)

:: Iniciar motor de VortexCore Hub en segundo plano
start "" "%PYTHON_EXE%" "%~dp0vortex_engine.py"
exit /b
