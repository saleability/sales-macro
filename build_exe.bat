@echo off
cd /d "%~dp0"
python -m pip install --quiet pyinstaller pynput
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "SalesMacro" ^
  --icon "assets\icon.ico" ^
  --add-data "assets\icon.ico;assets" ^
  sales_macro.py
echo.
echo Done. Your app is in the "dist" folder: dist\SalesMacro.exe
pause
