@echo off
setlocal
cd /d "%~dp0"
title Crear Acceso Directo de VortexCore Hub

set "PYTHON_EXE="
if exist "D:\Programacion\laragon\bin\python\python-3.13\python.exe" (
    set "PYTHON_EXE=D:\Programacion\laragon\bin\python\python-3.13\python.exe"
) else (
    where python >nul 2>&1 && for /f "delims=" %%i in ('where python') do set "PYTHON_EXE=%%i"
)

"%PYTHON_EXE%" "%~dp0create_shortcut.py"
pause
