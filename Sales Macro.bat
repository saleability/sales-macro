@echo off
cd /d "%~dp0"
python -c "import pynput" 2>nul || python -m pip install --quiet pynput
start "" pythonw sales_macro.py
