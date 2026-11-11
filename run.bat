@echo off
cd /d "%~dp0Source code"
py -m pip install -q -r requirements.txt
py macro_recorder.py
if errorlevel 1 pause
