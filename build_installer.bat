@echo off
title VortexCore Hub // Compilador de Instalador Oficial
cd /d "%~dp0"
echo =====================================================
echo   Iniciando compilacion de VortexCore Hub Setup...
echo =====================================================

REM Buscar Python local
set PYTHON_EXE=python
if exist "D:\Programacion\laragon\bin\python\python-3.13\python.exe" (
    set "PYTHON_EXE=D:\Programacion\laragon\bin\python\python-3.13\python.exe"
)

"%PYTHON_EXE%" build_installer.py
pause
