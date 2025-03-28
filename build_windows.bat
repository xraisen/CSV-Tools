@echo off
:: Build Windows executables for all CSV Tools scripts:
:: CSVProcessor, CSVSplitter, and CSV Search + AI
:: Requires Python and PyInstaller installed

:: Set up virtual environment
python -m venv venv
call venv\Scripts\activate.bat

:: Install dependencies
pip install --upgrade pip
pip install pandas pyinstaller

:: Create output directory if it doesn't exist
if not exist dist mkdir dist

:: Build csvprocessor.exe
pyinstaller --onefile --noconsole ^
            --name "CSVProcessor" ^
            --icon "assets\icon.ico" ^
            --add-data "assets;assets" ^
            csvprocessor.py

:: Build csvsplitter.exe
pyinstaller --onefile --noconsole ^
            --name "CSVSplitter" ^
            --icon "assets\icon.ico" ^
            --add-data "assets;assets" ^
            csvsplitter.py

:: Build csvsearchai.exe (CSV Search + AI - Gemini)
pyinstaller --onefile --noconsole ^
            --name "CSVSearchAI" ^
            --icon "assets\icon.ico" ^
            --add-data "assets;assets" ^
            csvsearchai.py

:: Copy executables to dist folder (if needed)
copy "dist\CSVProcessor.exe" "dist\"
copy "dist\CSVSplitter.exe" "dist\"
copy "dist\CSVSearchAI.exe" "dist\"

:: Create installer (optional)
:: Requires NSIS installed (https://nsis.sourceforge.io/Download)
makensis installer.nsi

pause
