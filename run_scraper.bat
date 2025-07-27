@echo off
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
    echo ✅ Python packages installed successfully
) else (
    echo ✅ Python packages already installed
)
echo.

echo [2/3] Checking Firefox browser...
where firefox >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ⚠️  Mozilla Firefox not found in PATH
    echo 💡 Please make sure Mozilla Firefox is installed
    echo    Download from: https://www.mozilla.org/firefox/
    echo.
    echo Continue anyway? Firefox may still work...
    pause
) else (
    echo ✅ Mozilla Firefox detected
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
