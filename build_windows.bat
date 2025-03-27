@echo off
:: Build Windows executables for both scripts
:: Requires Python and PyInstaller installed

:: Set up virtual environment
python -m venv venv
call venv\Scripts\activate.bat

:: Install dependencies
pip install --upgrade pip
pip install pandas pyinstaller

:: Create output directory
mkdir -p dist

:: Build csvprocessor.exe
pyinstaller --onefile --noconsole ^
            --name "CSVProcessor" ^
            --icon "assets/icon.ico" ^
            --add-data "assets;assets" ^
            csvprocessor.py

:: Build csvsplitter.exe
pyinstaller --onefile --noconsole ^
            --name "CSVSplitter" ^
            --icon "assets/icon.ico" ^
            --add-data "assets;assets" ^
            csvsplitter.py

:: Copy executables to dist folder
copy "dist\CSVProcessor.exe" "dist\"
copy "dist\CSVSplitter.exe" "dist\"

:: Create installer (optional)
:: Requires NSIS installed (https://nsis.sourceforge.io/Download)
makensis installer.nsi

pause