@echo off
cd /d "%~dp0"
title AI Message Aggregator

echo Starting AI Message Aggregator...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo Error during execution. Press any key to exit...
    pause > nul
)
