@echo off
setlocal enabledelayedexpansion

echo ================================================
echo   X/Twitter Mutual Followers Scraper
echo ================================================
echo.

echo [1/3] Checking Python dependencies...
python -c "import requests, selenium, webdriver_manager, bs4" 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing Python dependencies...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to install Python packages
        echo Make sure Python and pip are installed
        pause
        exit /b 1
    )
    echo [+] Python packages installed successfully
) else (
    echo [+] Python packages already installed
)
echo.

echo [2/3] Checking Firefox browser...
set FIREFOX_FOUND=0

REM Check common Firefox installation locations
set FIREFOX_LOCATIONS=^
"C:\Program Files\Mozilla Firefox\firefox.exe"

for %%f in (%FIREFOX_LOCATIONS%) do (
    if exist %%f (
        set FIREFOX_FOUND=1
        echo [+] Firefox detected: %%f
        goto :firefox_done
    )
)

echo [-] Firefox not found.

:firefox_done
if %FIREFOX_FOUND% equ 1 (
    echo [+] Firefox detected and ready for use
) else (
    echo [!] Firefox not detected by automatic checks. 
    echo     But we'll continue anyway since GeckoDriver can sometimes find Firefox automatically.
    echo     If the script fails, please install Firefox from:
    echo     https://www.mozilla.org/firefox/
    echo.
    echo     Press any key to continue...
    pause > nul
)
echo.

echo [3/3] Starting scraper...
echo GeckoDriver will be automatically downloaded when needed
echo ================================================
echo.

python scraper.py

echo.
echo ================================================
echo Scraper finished!
pause