@echo off
title REP Sim Bridge - DEMO
cd /d "%~dp0"
where py >nul 2>nul && (py -3 ponte.py --demo & goto fine)
where python >nul 2>nul && (python ponte.py --demo & goto fine)
echo.
echo  Python non e installato su questo PC.
echo  Scaricalo da https://www.python.org/downloads/ e durante l'installazione
echo  spunta "Add python.exe to PATH". Poi riapri questo file.
start https://www.python.org/downloads/
:fine
echo.
pause
