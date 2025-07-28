# XMutualFollowingScraper

A Python script that logs into X (formerly Twitter), retrieves your following and followers lists, and identifies mutual followers. It automatically downloads their profile pictures and sorts them by the date you followed each account.

## Features
- **Interactive Login**: Guides you through the X/Twitter login process
- **Smart Scrolling**: Automatically scrolls through all followers/following pages
- **Robust Profile Detection**: Uses multiple fallback methods to find profile pictures
- **High-Quality Images**: Downloads 400x400 profile pictures
- **Error Recovery**: Handles login expiration and network issues
- **Progress Tracking**: Real-time updates for easy monitoring
- **Results Export**: Saves complete results to JSON with timestamps

## Quick Start

### Option 1: One-click run
```powershell
# Double-click this file:
run_scraper.bat
```

### Option 2: Manual setup
```powershell
pip install -r requirements.txt
python scraper.py
```

## How It Works
- Here’s how it works:
- 1. You enter your @handle when prompted.
- 2. Firefox opens and takes you to the X login page.
- 3. After logging in, hit ENTER in the terminal.
- 4. The script fetches your following and followers lists.
- 5. It finds mutual followers, downloads their profile pictures, and names the files in the order you followed them.
- 6. You’ll end up with numbered images and a JSON file with details.

## Output Files
```
profile_pics/
├── 001_username1.jpg
├── 002_username2.jpg
├── 003_username3.jpg
└── ...

mutual_followers.json  # Complete results with metadata
```

## Configuration
Edit these settings in `scraper.py`:
```python
DOWNLOAD_DIR = 'profile_pics'     # Directory for downloaded images
SCROLL_PAUSE_TIME = 3             # Seconds to wait between scrolls
PROFILE_CHECK_DELAY = 10          # Seconds to wait between profile page loads
JSON_OUTPUT_FILE = 'mutual_following.json'  # Output JSON file path
```

## Requirements
- **Python 3.7+**
- **Mozilla Firefox browser** ([Download here](https://www.mozilla.org/firefox/) if not installed)
- **GeckoDriver** (automatically downloaded by the script)

## What Gets Installed Automatically
- **Python packages** (Selenium, requests, etc.) - via `pip install`
- **GeckoDriver** - automatically downloaded by WebDriverManager
- **Mozilla Firefox browser** - you need to install this manually

You only need to install **Mozilla Firefox browser** manually if you don't have it.

## Troubleshooting

### "No followers found"
- Make sure you're **fully logged in** to X/Twitter
- Check if the **target account is private**
- Verify the **username is correct** (no @ symbol needed)

## Authentication Required
To access your followers and following lists, you need to log in to X. Here’s how it works:
1. The script launches Firefox and opens the X login page.
2. You complete the login process (including any 2FA).
3. Press ENTER in the terminal to confirm you’re signed in.
4. The scraper resumes and begins collecting data.

### "Login verification failed"
- Complete the **entire login process** including any 2FA
- Make sure you can see your **home timeline** before pressing ENTER
- Try **refreshing the page** if login seems stuck

### Profile picture issues
- Some users may have **default avatars** only
- **Private accounts** may not allow image access
- **Rate limiting** may cause temporary failures

## Privacy & Security
- **No data sent externally** - everything stays on your computer
- **Your login credentials** are never stored or transmitted
- **Profile pictures** are downloaded directly from X/Twitter's CDN
- **Rate limiting** built-in to be respectful to X/Twitter's servers

## Performance Tips
- **Stable internet connection** recommended
- **Don't minimize** the browser window during scraping
- **Larger accounts** (1000+ followers) may take 10-30 minutes
- **Close other browser tabs** for better performance

## Support the Project

If you find this tool helpful, consider supporting its development:

<a href="https://venmo.com/u/konekuro" target="_blank">
  <img src="https://img.shields.io/badge/Venmo-Support%20Development-3D95CE?style=for-the-badge&logo=venmo&logoColor=white" alt="Support on Venmo" />
</a>


