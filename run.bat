@echo off
cd /d "c:\Users\BKMZ\.gemini\antigravity-ide\scratch\ai-message-aggregator"
title AI Message Aggregator

echo Starting AI Message Aggregator...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo Error during execution. Press any key to exit...
    pause > nul
)
