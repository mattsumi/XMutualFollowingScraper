import os
import requests
import json
import shutil
import tempfile
import platform
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.firefox import GeckoDriverManager
import time
import re

# --- CONFIG ---
USERNAME = input("Enter your X/Twitter username (without @): ").strip()
print("\nWhat would you like to download?")
print("1. Only mutual followers (people who follow you back)")
print("2. All followers (both mutual and non-mutual)")
print("3. Both - separate files for mutuals and non-mutuals")
download_choice = input("Enter your choice (1, 2, or 3): ").strip()

DOWNLOAD_DIR = 'profile_pics'
SCROLL_PAUSE_TIME = 3      # Time to wait between scrolls (increased for rate limiting)
PROFILE_CHECK_DELAY = 10    # Delay between profile visits to avoid 429 errors
JSON_OUTPUT_FILE = 'mutual_following.json'  # JSON output file
NO_NEW_USERS_LIMIT = 5     # Stop scrolling after this many attempts with no new users

# --- SETUP ---
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def find_firefox_profile():
    """Find Firefox profile directories and let user choose which version to use"""
    system = platform.system()
    
    if system == "Windows":
        appdata = Path(os.environ.get('APPDATA', ''))
        main_profile_dir = appdata / 'Mozilla' / 'Firefox' / 'Profiles'
        
        if not main_profile_dir.exists():
            print("\n[!] No Firefox profiles directory found")
            return None
        
        # Get all profiles
        all_profiles = [p for p in main_profile_dir.iterdir() if p.is_dir() and not p.name.startswith('.')]
        
        if not all_profiles:
            print("\n[!] No Firefox profiles found")
            return None
        
        # Categorize profiles by variant based on naming patterns
        available_variants = []
        
        for profile in all_profiles:
            profile_name = profile.name
            mtime = profile.stat().st_mtime
            
            # Determine variant based on profile name
            if 'dev-edition' in profile_name.lower():
                variant_name = 'Firefox Developer Edition'
            elif 'nightly' in profile_name.lower():
                variant_name = 'Firefox Nightly'
            elif 'esr' in profile_name.lower():
                variant_name = 'Firefox ESR'
            elif 'default' in profile_name.lower():
                variant_name = 'Firefox'
            else:
                variant_name = 'Firefox (Custom Profile)'
            
            available_variants.append({
                'name': variant_name,
                'profile': profile,
                'profile_name': profile_name,
                'mtime': mtime
            })
        
    elif system == "Darwin":  # macOS
        base = Path.home() / 'Library' / 'Application Support'
        firefox_variants = [
            ('Firefox', base / 'Firefox' / 'Profiles'),
            ('Firefox Developer Edition', base / 'Firefox Developer Edition' / 'Profiles'),
            ('Firefox Nightly', base / 'Firefox Nightly' / 'Profiles'),
            ('Firefox ESR', base / 'Firefox ESR' / 'Profiles'),
        ]
        
        available_variants = []
        for variant_name, profile_base in firefox_variants:
            if profile_base.exists():
                profiles = list(profile_base.glob('*.default*'))
                if not profiles:
                    profiles = [p for p in profile_base.iterdir() if p.is_dir() and not p.name.startswith('.')]
                
                if profiles:
                    profiles.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    available_variants.append({
                        'name': variant_name,
                        'profile': profiles[0],
                        'profile_name': profiles[0].name,
                        'mtime': profiles[0].stat().st_mtime
                    })
        
    elif system == "Linux":
        home = Path.home()
        firefox_variants = [
            ('Firefox', home / '.mozilla' / 'firefox'),
            ('Firefox Developer Edition', home / '.mozilla' / 'firefox-dev'),
            ('Firefox Nightly', home / '.mozilla' / 'firefox-nightly'),
            ('Firefox ESR', home / '.mozilla' / 'firefox-esr'),
        ]
        
        available_variants = []
        for variant_name, profile_base in firefox_variants:
            if profile_base.exists():
                profiles = list(profile_base.glob('*.default*'))
                if not profiles:
                    profiles = [p for p in profile_base.iterdir() if p.is_dir() and not p.name.startswith('.')]
                
                if profiles:
                    profiles.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    available_variants.append({
                        'name': variant_name,
                        'profile': profiles[0],
                        'profile_name': profiles[0].name,
                        'mtime': profiles[0].stat().st_mtime
                    })
    else:
        print(f"[!] Unsupported operating system: {system}")
        return None
    
    if not available_variants:
        print("\n[!] No Firefox profiles found")
        return None
    
    # Sort by modification time (most recent first)
    available_variants.sort(key=lambda v: v['mtime'], reverse=True)
    
    # Let user choose which Firefox version to use
    print("\n[!] Found the following Firefox profiles:")
    for idx, variant in enumerate(available_variants, 1):
        print(f"  {idx}. {variant['name']}")
        print(f"     Profile: {variant['profile_name']}")
    
    default_choice = 1
    print(f"\n[!] Most recently used: {available_variants[0]['name']}")
    
    while True:
        choice = input(f"Enter your choice (1-{len(available_variants)}) or press Enter for default [{default_choice}]: ").strip()
        
        if choice == '':
            choice = default_choice
            break
        
        try:
            choice = int(choice)
            if 1 <= choice <= len(available_variants):
                break
            else:
                print(f"[!] Please enter a number between 1 and {len(available_variants)}")
        except ValueError:
            print("[!] Please enter a valid number")
    
    selected = available_variants[choice - 1]
    print(f"[+] Using {selected['name']}: {selected['profile_name']}")
    return selected['profile']

def copy_firefox_profile(source_profile):
    """Create a temporary copy of the Firefox profile for use with Selenium"""
    if not source_profile or not source_profile.exists():
        print("[!] Source profile does not exist")
        return None
    
    try:
        # Create a temporary directory for the profile copy
        temp_dir = tempfile.mkdtemp(prefix='firefox_profile_')
        temp_profile = Path(temp_dir)
        
        print(f"[!] Copying Firefox profile to temporary location...")
        print(f"[!] This may take a moment...")
        
        # Files and directories essential for login session
        essential_items = [

            'cookies.sqlite',
            'cookies.sqlite-shm',
            'cookies.sqlite-wal',
            'key4.db',              # Password/login storage
            'key3.db',              # Legacy key storage
            'logins.json',          # Login credentials
            'cert9.db',             # Certificates
            'cert8.db',             # Legacy certificates
            'prefs.js',             # Preferences
            'user.js',              # User preferences
            'permissions.sqlite',   # Site permissions
            'content-prefs.sqlite', # Content preferences
            'webappsstore.sqlite',  # Local storage
            'sessionstore.jsonlz4', # Session data
            'sessionstore.js',      # Legacy session data
            'sessionstore-backups', # Session backups directory
            'storage',              # Storage directory (important for login tokens)
            'storage.sqlite',       # Storage database
        ]
        
        # Copy essential files and directories
        copied_count = 0
        for item_name in essential_items:
            source_item = source_profile / item_name
            dest_item = temp_profile / item_name
            
            if source_item.exists():
                try:
                    if source_item.is_dir():
                        # Copy entire directory
                        shutil.copytree(source_item, dest_item, ignore_dangling_symlinks=True)
                        copied_count += 1
                    else:
                        # Copy file
                        dest_item.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_item, dest_item)
                        copied_count += 1
                except Exception as e:
                    # Continue even if some files fail
                    pass
        
        print(f"[+] Copied {copied_count}/{len(essential_items)} profile items")
        
        if copied_count > 0:
            return temp_profile
        else:
            print("[!] No profile files were copied")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None
            
    except Exception as e:
        print(f"[!] Error copying Firefox profile: {e}")
        import traceback
        print(f"[!] Traceback: {traceback.format_exc()}")
        return None

def setup_driver():
    """Setup Firefox WebDriver with optimal settings for Twitter scraping"""
    print("[!] Setting up Firefox WebDriver...")
    
    # Try to find and copy user's Firefox profile
    firefox_profile = find_firefox_profile()
    temp_profile = None
    
    if firefox_profile:
        print("[!] Attempting to use your existing Firefox profile for automatic login...")
        temp_profile = copy_firefox_profile(firefox_profile)
        if temp_profile:
            print("[+] Firefox profile copied successfully - you may already be logged in!")
        else:
            print("[!] Could not copy profile - you'll need to log in manually")
    else:
        print("[!] No Firefox profile found - you'll need to log in manually")
    
    try:
        service = Service(GeckoDriverManager().install())
        print("[+] GeckoDriver installed/updated successfully")
    except Exception as e:
        print(f"[!] WebDriverManager failed, trying default GeckoDriver: {e}")
        service = None
    
    firefox_options = Options()
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--disable-dev-shm-usage')
    firefox_options.set_preference('dom.webdriver.enabled', False)
    firefox_options.set_preference('useAutomationExtension', False)
    firefox_options.set_preference('general.useragent.override', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0')
    
    firefox_options.add_argument('--disable-logging')
    firefox_options.add_argument('--log-level=3')  # Only show fatal errors
    firefox_options.add_argument('--silent')
    firefox_options.set_preference('media.volume_scale', '0.0')  # Mute audio
    firefox_options.set_preference('browser.startup.homepage', 'about:blank')
    firefox_options.set_preference('startup.homepage_welcome_url', 'about:blank')
    firefox_options.set_preference('startup.homepage_override_url', 'about:blank')
    firefox_options.set_preference('privacy.trackingprotection.enabled', False)
    firefox_options.set_preference('browser.safebrowsing.enabled', False)
    firefox_options.set_preference('browser.safebrowsing.malware.enabled', False)
    firefox_options.set_preference('browser.tabs.animate', False)
    firefox_options.set_preference('browser.fullscreen.animateUp', 0)
    firefox_options.set_preference('browser.cache.disk.enable', False)
    firefox_options.set_preference('browser.cache.memory.enable', False)
    firefox_options.set_preference('browser.sessionstore.max_tabs_undo', 0)
    
    # Use the copied profile if available
    if temp_profile:
        firefox_options.add_argument('-profile')
        firefox_options.add_argument(str(temp_profile))
        print(f"[+] Using profile: {temp_profile}")

    try:
        if service:
            driver = webdriver.Firefox(service=service, options=firefox_options)
        else:
            driver = webdriver.Firefox(options=firefox_options)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print("[+] Firefox browser launched successfully")
        
        # Store temp profile path in driver for cleanup later
        driver.temp_profile_path = temp_profile
        
        return driver
        
    except Exception as e:
        # Cleanup temp profile if driver creation failed
        if temp_profile and temp_profile.exists():
            try:
                shutil.rmtree(temp_profile, ignore_errors=True)
            except:
                pass
        
        print(f"[!?] Failed to start Firefox WebDriver: {e}")
        print("\n[!] TROUBLESHOOTING:")
        print("1. Make sure Mozilla Firefox browser is installed")
        print("2. Try updating Firefox to the latest version")
        print("3. Restart your computer and try again")
        print("4. If you don't have Firefox, download it from: https://www.mozilla.org/firefox/")
        raise

def login_to_twitter(driver):
    """Navigate to Twitter login and wait for user to log in manually"""
    print("\n[!] Checking login status...")
    
    # First, try to navigate to the home page to check if already logged in
    driver.get('https://x.com/home')
    time.sleep(5)  # Wait for page to load
    
    # Check if already logged in
    logged_in_elements = [
        '[data-testid="SideNav_AccountSwitcher_Button"]',
        '[data-testid="AppTabBar_Profile_Link"]', 
        '[aria-label="Profile"]',
        '[data-testid="primaryColumn"]',
        '[data-testid="composeTweet"]',
        '[aria-label="Home timeline"]'
    ]
    
    for selector in logged_in_elements:
        try:
            element = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            if element:
                print("[+] Already logged in! Using existing session.")
                return True
        except TimeoutException:
            continue
    
    # Not logged in, proceed with manual login
    print("\n[!] LOGIN REQUIRED")
    print("=" * 50)
    print("X/Twitter requires you to be logged in to view following lists.")
    print("The browser will now open to X/Twitter login page.")
    print("Please log in manually and then the script will automatically continue.")
    print("=" * 50)
    
    # Navigate to login page
    driver.get('https://x.com/login')
    
    # Wait for user to log in automatically by checking for login success
    print("\n[!] Please log in to X/Twitter in the browser window...")
    print("[!] Script will automatically continue once login is detected...")
    
    # Wait for login to complete by checking for logged-in elements
    max_wait_time = 300  
    check_interval = 10 
    
    for attempt in range(0, max_wait_time, check_interval):
        try:
            current_url = driver.current_url.lower()
            print(f"[!] Current URL: {current_url}")
            
            if 'login' not in current_url:
                try:
                    for selector in logged_in_elements:
                        try:
                            element = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            if element:
                                print("[+] Login successful!")
                                return True
                        except TimeoutException:
                            continue
                    
                    print("[!] Not on login page but no login elements found. Trying home page...")
                    driver.get('https://x.com/home')
                    time.sleep(5)
                    
                    for selector in logged_in_elements:
                        try:
                            element = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            if element:
                                print("[+] Login successful!")
                                return True
                        except TimeoutException:
                            continue
                            
                except Exception as e:
                    print(f"[!] Error checking login elements: {e}")
            
            if attempt < max_wait_time - check_interval:
                print(f"[!] Still waiting for login... ({attempt + check_interval}s elapsed)")
                time.sleep(check_interval)
            
        except Exception as e:
            print(f"[!] Error checking login status: {e}")
            time.sleep(check_interval)
            continue
    
    print("[!?] Login timeout. Please make sure you're logged in and try again.")
    return False

def scroll_and_collect_users_with_dates(driver, page_type="followers"):
    """Scroll through a list and collect user handles with their follow dates - complete single pass"""
    users_data = []
    last_height = driver.execute_script("return document.body.scrollHeight")
    no_new_users_count = 0
    stagnant_height_count = 0
    scroll_count = 0
    
    print(f"[!] Starting comprehensive single-pass scroll through {page_type} list...")
    
    # Ensure we're in the correct section before starting
    if not is_actual_follower_section(driver):
        print(f"[!] Warning: May not be in actual {page_type} section")
    
    print("[!] Collecting initially visible users before scrolling...")
    try:
        # Only collect from the main column, avoid sidebar suggestions
        main_column = driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
        user_cells = main_column.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
        print(f"[!] Found {len(user_cells)} UserCell elements in main column on initial view")
        if user_cells:
            collect_users_from_cells(user_cells, users_data)
        
        if len(users_data) == 0:
            try_alternative_selectors(driver, users_data)
            
        print(f"[+] Collected {len(users_data)} users from initial view before scrolling")
    except Exception as e:
        print(f"[!] Error collecting initial users: {e}")
        # Fallback to original method if main column not found
        try:
            user_cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
            print(f"[!] Fallback: Found {len(user_cells)} UserCell elements on initial view")
            if user_cells:
                collect_users_from_cells(user_cells, users_data)
        except Exception as e2:
            print(f"[!] Fallback also failed: {e2}")
    
    while True:
        scroll_count += 1
        print(f"[!] Scroll #{scroll_count} - Current users: {len(users_data)}")
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        
        old_count = len(users_data)
        try:
            # Strategy 1: Look for UserCell elements in main column (most reliable)
            try:
                main_column = driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
                user_cells = main_column.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                print(f"[!] Found {len(user_cells)} UserCell elements in main column on current view")
            except:
                # Fallback to all UserCells if main column not found
                user_cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                print(f"[!] Fallback: Found {len(user_cells)} UserCell elements on current view")
            
            collect_users_from_cells(user_cells, users_data)
                    
            # Strategy 2: Fallback detection methods
            if len(users_data) == old_count:
                print("[!] UserCell method found no new users, trying fallback methods...")
                try_alternative_selectors(driver, users_data)
                        
        except (TimeoutException, NoSuchElementException) as e:
            print(f"[!?] Error collecting users: {e}")
        
        # Check if we found new users
        new_count = len(users_data)
        if new_count == old_count:
            no_new_users_count += 1
            print(f"[!] No new users found in this scroll (attempt {no_new_users_count}/{NO_NEW_USERS_LIMIT})")
            
            # Try more aggressive scrolling when we don't find new users
            if no_new_users_count <= 3:
                print(f"[!] Trying a larger scroll to find more users...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight + 2000);")
                time.sleep(SCROLL_PAUSE_TIME * 2)
                
                # Try clicking any "Show more" or "Load more" buttons
                try:
                    load_more_texts = ["Show more", "Load more", "See more"]
                    for text in load_more_texts:
                        buttons = driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
                        for button in buttons:
                            try:
                                if button.is_displayed() and button.is_enabled():
                                    driver.execute_script("arguments[0].scrollIntoView();", button)
                                    time.sleep(1)
                                    driver.execute_script("arguments[0].click();", button)
                                    print(f"[+] Clicked '{text}' button")
                                    time.sleep(SCROLL_PAUSE_TIME)
                                    break
                            except:
                                continue
                except Exception as e:
                    print(f"[!] Error trying to click load more buttons: {e}")
            else:
                # Even more aggressive final attempts
                print(f"[!] Trying very aggressive scrolling for final attempts...")
                for i in range(3):
                    driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight + {3000 + (i * 1000)});")
                    time.sleep(SCROLL_PAUSE_TIME)
                    
                    # Check for more users after aggressive scroll
                    temp_old_count = len(users_data)
                    try:
                        main_column = driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
                        user_cells = main_column.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                        collect_users_from_cells(user_cells, users_data)
                    except:
                        user_cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                        collect_users_from_cells(user_cells, users_data)
                    
                    if len(users_data) > temp_old_count:
                        print(f"[+] Aggressive scroll found {len(users_data) - temp_old_count} more users!")
                        no_new_users_count = 0  # Reset counter
                        break
        else:
            no_new_users_count = 0
            print(f"[+] Found {new_count - old_count} new users in this scroll")
            
        print(f"[+] Collected {len(users_data)} users so far (scroll #{scroll_count})")
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            stagnant_height_count += 1
            print(f"[!] Page height unchanged (attempt {stagnant_height_count}/3)")
        else:
            stagnant_height_count = 0
            last_height = new_height
            
        if no_new_users_count >= NO_NEW_USERS_LIMIT or stagnant_height_count >= 5:
            if no_new_users_count >= NO_NEW_USERS_LIMIT:
                print(f"[-] No new users found after {no_new_users_count} consecutive scrolls - stopping collection")
            else:
                print(f"[-] Page height unchanged after {stagnant_height_count} consecutive scrolls - likely reached end of list")
            
            # Final verification: try one more time with different approach
            print("[!] Performing final verification scroll...")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight + 5000);")
            time.sleep(SCROLL_PAUSE_TIME * 2)
            
            final_old_count = len(users_data)
            try:
                main_column = driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
                user_cells = main_column.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                collect_users_from_cells(user_cells, users_data)
            except:
                user_cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
                collect_users_from_cells(user_cells, users_data)
            
            if len(users_data) > final_old_count:
                print(f"[+] Final verification found {len(users_data) - final_old_count} more users!")
                no_new_users_count = 0
                stagnant_height_count = 0
                continue
                
            print(f"[+] Completed scroll with {scroll_count} total scrolls")
            break
        else:
            stagnant_height_count = 0
            last_height = new_height
        
        try:
            show_more_selectors = [
                '[role="button"]:has-text("Show more")', 
                '[role="button"]:has-text("Load more")',
                'div[aria-label="Load more"]',
                'span:contains("Show more")',
                'div:contains("Show")'
            ]
            
            for selector in show_more_selectors:
                try:
                    show_more_buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                    if show_more_buttons:
                        print(f"[!] Found 'Show more' button, attempting to click...")
                        for button in show_more_buttons:
                            try:
                                if button.is_displayed() and button.is_enabled():
                                    driver.execute_script("arguments[0].click();", button)
                                    print(f"[+] Clicked 'Show more' button")
                                    time.sleep(SCROLL_PAUSE_TIME)  # Wait for more content to load
                                    break
                            except:
                                continue
                except:
                    pass
        except Exception as e:
            print(f"[!] Error trying to click 'Show more' button: {e}")
        
        # Additional check: try to detect "end of list" indicators more reliably
        try:
            page_source = driver.page_source.lower()
            end_indicators = [
                "you've reached the end",
                "no more to show",
                "that's all",
                "end of list",
                "nothing more to load",
                "end of timeline",
                "no more followers",
                "no more following",
                "you've seen it all"
            ]
            
            for indicator in end_indicators:
                if indicator in page_source:
                    print(f"[-] Detected end-of-list indicator: '{indicator}'")
                    print(f"[+] Completed scroll with {scroll_count} total scrolls")
                    return users_data
                    
        except Exception:
            pass
            
        # Safety valve: if we've scrolled excessively (100+ times), something might be wrong
        if scroll_count > 100:
            print(f"[-] Safety stop at {scroll_count} scrolls - this seems excessive")
            print(f"[+] Completed scroll with {scroll_count} total scrolls")
            break
    
    print(f"[+] Completed single-pass scroll with {scroll_count} total scrolls")
    return users_data

def is_valid_user_link(href):
    """Check if a href is a valid user profile link"""
    invalid_patterns = ['/status/', '/photo/', '/search', '/hashtag/', '/i/', '/intent/', '/compose/']
    return not any(pattern in href for pattern in invalid_patterns)

def extract_username_from_url(href):
    """Extract username from profile URL"""
    if href.count('/') >= 3:
        return href.split('/')[-1] if not href.endswith('/') else href.split('/')[-2]
    return None

def is_valid_username(username):
    """Check if username is valid"""
    invalid_usernames = ['home', 'notifications', 'explore', 'messages', 'bookmarks', 'lists', 'profile', 'more', 'settings', 'help']
    return (username and 
            len(username) > 0 and 
            not username.startswith('i') and 
            username not in invalid_usernames and
            not username.isdigit())

def extract_follow_date(cell, position):
    """Extract follow date from cell element"""
    try:
        # Look for time elements or date indicators
        time_elements = cell.find_elements(By.CSS_SELECTOR, 'time')
        if time_elements:
            return time_elements[0].get_attribute('datetime')
    except:
        pass
    # Fallback: use position
    return f"position_{position}"

def is_suggestion_section(cell):
    """Check if a UserCell is part of a suggestion/recommendation section"""
    try:
        # Check parent containers for suggestion indicators
        parent = cell
        for _ in range(5):  # Check up to 5 levels up
            try:
                parent = parent.find_element(By.XPATH, "./..")
                parent_text = parent.text.lower()
                
                # Look for suggestion section indicators
                suggestion_indicators = [
                    'you might like',
                    'recommended for you',
                    'who to follow',
                    'suggested for you',
                    'people you may know',
                    'discover more',
                    'follow more people',
                    'suggestions',
                    'recommended'
                ]
                
                for indicator in suggestion_indicators:
                    if indicator in parent_text:
                        return True
                        
                # Check for specific data attributes that indicate suggestions
                parent_html = parent.get_attribute('outerHTML')
                if parent_html:
                    suggestion_attributes = [
                        'data-testid="sidebarColumn"',
                        'data-testid="placementTracking"',
                        'data-testid="UserRecommendations"',
                        'aria-label="Timeline: Trending now"',
                        'aria-label="Who to follow"'
                    ]
                    
                    for attr in suggestion_attributes:
                        if attr in parent_html:
                            return True
            except:
                break
                
        # Additional check: look for suggestion indicators in nearby text
        try:
            # Get the preceding sibling elements to check for headers
            preceding_elements = cell.find_elements(By.XPATH, "./preceding-sibling::*[position()<=3]")
            for element in preceding_elements:
                element_text = element.text.lower()
                if any(indicator in element_text for indicator in ['you might like', 'recommended', 'suggestions', 'who to follow']):
                    return True
        except:
            pass
            
    except Exception:
        pass
    
    return False

def is_actual_follower_section(driver):
    """Check if we're currently in the actual followers/following section"""
    try:
        # Check the current URL to make sure we're on a followers/following page
        current_url = driver.current_url.lower()
        if not ('/followers' in current_url or '/following' in current_url):
            return False
            
        # Look for main timeline container
        main_containers = driver.find_elements(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
        if not main_containers:
            return False
            
        # Check that we're not in a suggestion sidebar
        try:
            sidebar_suggestions = driver.find_elements(By.CSS_SELECTOR, '[data-testid="sidebarColumn"]')
            return True  # Main column exists, sidebar is separate
        except:
            return True
            
    except Exception:
        return False

def get_display_name_from_cell(cell):
    """Extract display name from a user cell"""
    try:
        # Method 1: Try to find the first link's span (most robust)
        link = cell.find_element(By.CSS_SELECTOR, 'a[role="link"]:not([tabindex="-1"])')
        if link:
            span = link.find_element(By.TAG_NAME, 'span')
            if span and span.text.strip():
                return span.text.strip()
    except:
        pass
    
    try:
        # Method 2: Look for spans in the cell and find the one that looks like a display name
        # Display names are typically in larger, bolder text
        spans = cell.find_elements(By.TAG_NAME, 'span')
        for span in spans:
            text = span.text.strip()
            # Display name is usually not empty, not starting with @, and not a button text
            if text and not text.startswith('@') and text not in ['Following', 'Follow', 'Follows you']:
                # Additional check: display name shouldn't be too long (usually < 50 chars)
                if len(text) < 50:
                    return text
    except:
        pass
    
    return ''

def collect_users_from_cells(user_cells, users_data):
    """Process user cells and extract user information, filtering out suggestions"""
    actual_followers_count = 0
    suggestions_filtered = 0
    
    for cell in user_cells:
        try:
            # First, check if this cell is part of a suggestion section
            if is_suggestion_section(cell):
                suggestions_filtered += 1
                continue
                
            # Check if this cell has the "Follows you" indicator (mutual follow)
            follows_you_indicator = cell.find_elements(By.CSS_SELECTOR, '[data-testid="userFollowIndicator"]')
            is_mutual = len(follows_you_indicator) > 0
            
            # Find username link - try multiple approaches
            username_links = cell.find_elements(By.CSS_SELECTOR, 'a[href^="/"]')
            for username_link in username_links:
                href = username_link.get_attribute('href')
                
                if href and is_valid_user_link(href):
                    username = extract_username_from_url(href)
                    
                    if username and is_valid_username(username):
                        # Check if we already have this user
                        if not any(user['username'] == username for user in users_data):
                            # Get display name
                            display_name = get_display_name_from_cell(cell)
                            
                            # Try to find follow date or any timestamp info
                            follow_date = extract_follow_date(cell, len(users_data))
                            
                            # Try to extract profile picture URL from the cell (non-verbose for speed)
                            profile_pic_url = extract_profile_pic_from_cell(cell, verbose=False)
                            
                            # Construct profile URL
                            profile_url = f"https://x.com/{username}"
                            
                            users_data.append({
                                'displayName': display_name,
                                'username': username,
                                'url': profile_url,
                                'follow_date': follow_date,
                                'position': len(users_data),
                                'is_mutual': is_mutual,
                                'profile_pic_url': profile_pic_url
                            })
                            actual_followers_count += 1
                            pic_status = "[+]" if profile_pic_url else "[-]"
                            mutual_status = "MUTUAL" if is_mutual else "not mutual"
                            display_info = f" ({display_name})" if display_name else ""
                            print(f"[+] Added user: {username}{display_info} (position {len(users_data)}) - {mutual_status} - Pic: {pic_status}")
                            break  # Found a valid user in this cell, move to next cell
        except Exception as e:
            print(f"[!] Error processing cell: {e}")
            continue
    
    if suggestions_filtered > 0:
        print(f"[!] Filtered out {suggestions_filtered} suggested users, added {actual_followers_count} actual followers")

def try_alternative_selectors(driver, users_data):
    """Try alternative selectors to find users, avoiding suggestion sections"""
    # Focus on main column first
    try:
        main_column = driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
        print("[!] Trying alternative selectors within main column...")
        
        selectors = [
            '[data-testid="cellInnerDiv"] a[href^="/"]',
            'div[dir="ltr"] a[href^="/"]',
            'a[role="link"][href^="/"]',
            'a[href*="/"][role="link"]'
        ]
        
        for selector in selectors:
            user_links = main_column.find_elements(By.CSS_SELECTOR, selector)
            print(f"[!] Trying selector '{selector}' in main column - found {len(user_links)} links")
            
            for link in user_links:
                try:
                    href = link.get_attribute('href')
                    if href and is_valid_user_link(href):
                        username = extract_username_from_url(href)
                        if username and is_valid_username(username):
                            if not any(user['username'] == username for user in users_data):
                                # Try to find the parent cell for profile pic extraction
                                is_mutual = False
                                profile_pic_url = None
                                display_name = ''
                                try:
                                    parent_cell = link.find_element(By.XPATH, "./ancestor::*[@data-testid='UserCell']")
                                    
                                    # Check if this is a suggestion
                                    if is_suggestion_section(parent_cell):
                                        continue
                                    
                                    # Check for mutual follow indicator
                                    follows_you_indicator = parent_cell.find_elements(By.CSS_SELECTOR, '[data-testid="userFollowIndicator"]')
                                    is_mutual = len(follows_you_indicator) > 0
                                    
                                    # Get display name
                                    display_name = get_display_name_from_cell(parent_cell)
                                        
                                    profile_pic_url = extract_profile_pic_from_cell(parent_cell, verbose=False)
                                except:
                                    pass
                                
                                # Construct profile URL
                                profile_url = f"https://x.com/{username}"
                                    
                                users_data.append({
                                    'displayName': display_name,
                                    'username': username,
                                    'url': profile_url,
                                    'follow_date': f"position_{len(users_data)}",
                                    'position': len(users_data),
                                    'is_mutual': is_mutual,
                                    'profile_pic_url': profile_pic_url
                                })
                                pic_status = "[+]" if profile_pic_url else "[-]"
                                mutual_status = "MUTUAL" if is_mutual else "not mutual"
                                display_info = f" ({display_name})" if display_name else ""
                                print(f"[+] Added user (fallback): {username}{display_info} - {mutual_status} - Pic: {pic_status}")
                except Exception:
                    continue
            
            if len(users_data) > 0:
                break  # Found some users with this selector
                
    except Exception as e:
        print(f"[!] Main column not found, trying global fallback: {e}")
        
        # Global fallback if main column not accessible
        selectors = [
            '[data-testid="cellInnerDiv"] a[href^="/"]',
            'div[dir="ltr"] a[href^="/"]',
            'a[role="link"][href^="/"]',
            'a[href*="/"][role="link"]',
            'a[href^="/"]'
        ]
        
        for selector in selectors:
            user_links = driver.find_elements(By.CSS_SELECTOR, selector)
            print(f"[!] Trying global selector '{selector}' - found {len(user_links)} links")
            
            suggestions_skipped = 0
            for link in user_links:
                try:
                    # Check if link is in sidebar or suggestion area
                    try:
                        sidebar_parent = link.find_element(By.XPATH, "./ancestor::*[@data-testid='sidebarColumn']")
                        if sidebar_parent:
                            suggestions_skipped += 1
                            continue  # Skip sidebar suggestions
                    except:
                        pass  # Not in sidebar, continue processing
                        
                    href = link.get_attribute('href')
                    if href and is_valid_user_link(href):
                        username = extract_username_from_url(href)
                        if username and is_valid_username(username):
                            if not any(user['username'] == username for user in users_data):
                                # Try to find the parent cell for profile pic extraction
                                try:
                                    parent_cell = link.find_element(By.XPATH, "./ancestor::*[@data-testid='UserCell']")
                                    profile_pic_url = extract_profile_pic_from_cell(parent_cell, verbose=False)
                                except:
                                    profile_pic_url = None
                                    
                                users_data.append({
                                    'username': username,
                                    'follow_date': f"position_{len(users_data)}",
                                    'position': len(users_data),
                                    'has_status_indicator': False,
                                    'profile_pic_url': profile_pic_url
                                })
                                pic_status = "[+]" if profile_pic_url else "[-]"
                                print(f"[+] Added user (global fallback): {username} - Pic: {pic_status}")
                except Exception:
                    continue
            
            if suggestions_skipped > 0:
                print(f"[!] Skipped {suggestions_skipped} sidebar suggestions in global fallback")
            
            if len(users_data) > 0:
                break  # Found some users with this selector

def is_valid_twitter_profile_url(url, verbose=True):
    """Check if a URL is a valid Twitter profile image URL"""
    if not url:
        return False
    
    # Must be a proper HTTP/HTTPS URL
    if not url.startswith(('http://', 'https://')):
        if verbose:
            print(f"     [-] Invalid URL scheme: {url}")
        return False
    
    # Must be from Twitter's CDN
    if 'pbs.twimg.com' not in url or 'profile_images' not in url:
        if verbose:
            print(f"     [-] Not a Twitter profile image URL: {url}")
        return False
    
    # Should not be a data URL or other invalid format
    if url.startswith('data:'):
        if verbose:
            print(f"     [-] Data URL not supported: {url[:50]}...")
        return False
    
    return True

def extract_profile_pic_from_cell(cell, verbose=True):
    """Extract profile picture URL from a UserCell element - Firefox compatible with optional debugging"""
    try:
        if verbose:
            print(f"     [!] Searching for profile pic in UserCell...")
        # Look for profile images in the cell with Firefox-compatible selectors
        img_selectors = [
            'img[src*="profile_images"]',
            'img[src*="pbs.twimg.com"]',
            '[data-testid*="Avatar"] img',
            '[data-testid="UserAvatar-Container"] img',
            'img[alt*="profile"]',
            'div img[src*="twimg"]',
            'img'
        ]
        
        for selector_idx, selector in enumerate(img_selectors, 1):
            try:
                if verbose:
                    print(f"     [!] Trying selector {selector_idx}: {selector}")
                images = cell.find_elements(By.CSS_SELECTOR, selector)
                if verbose:
                    print(f"     [!] Found {len(images)} images with this selector")
                
                for img_idx, img in enumerate(images, 1):
                    try:
                        src = img.get_attribute('src')
                        if verbose:
                            print(f"     [!] Image {img_idx} src: {src}")
                        
                        if src and is_valid_twitter_profile_url(src, verbose=verbose):
                            # Convert to highest quality version (original size)
                            pic_url = re.sub(r'_\d+x\d+', '_400x400', src)  # Start with 400x400
                            pic_url = re.sub(r'_normal', '_400x400', pic_url)  # Replace _normal with _400x400
                            pic_url = re.sub(r'_bigger', '_400x400', pic_url)  # Replace _bigger with _400x400
                            pic_url = re.sub(r'_mini', '_400x400', pic_url)   # Replace _mini with _400x400
                            
                            # Try to get even higher quality by removing size restrictions entirely
                            high_quality_url = re.sub(r'_400x400', '', pic_url)
                            
                            if verbose:
                                print(f"     [+] Found valid profile pic: {high_quality_url}")
                            return high_quality_url
                    except Exception as e:
                        if verbose:
                            print(f"     [!] Error processing image {img_idx}: {e}")
                        continue
            except Exception as e:
                if verbose:
                    print(f"     [!] Error with selector {selector_idx}: {e}")
                continue
        
        if verbose:
            print(f"     [-] No profile picture found in UserCell")
    except Exception as e:
        if verbose:
            print(f"     [!?] Error in extract_profile_pic_from_cell: {e}")
    return None

def get_following(driver, username):
    """Get all following for a given username"""
    url = f'https://x.com/{username}/following'
    print(f"[!] Navigating to following page: {url}")
    driver.get(url)
    
    # Wait for page to load and check if login is required
    try:
        WebDriverWait(driver, 10).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="primaryColumn"]')),
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="loginButton"]')),
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="text"]'))  # Login form
            )
        )
        
        # Check if we're redirected to login
        if 'login' in driver.current_url.lower() or driver.find_elements(By.CSS_SELECTOR, '[data-testid="loginButton"]'):
            print("[!?] Not logged in or session expired. Please log in again.")
            return []
            
    except TimeoutException:
        print("[!?] Timeout waiting for following page to load")
        return []
    
    time.sleep(5)  # Additional wait for dynamic content
    
    print(f"[!] Checking page content for user: {username}")
    
    # Check if the following list is completely inaccessible (but allow private accounts in list)
    page_content = driver.page_source.lower()
    
    # Debug: Print current URL and check for common error indicators
    print(f"[!] Current URL: {driver.current_url}")
    
    # Only check for complete privacy restrictions, not individual private followers
    complete_privacy_indicators = [
        "isn't available",
        "these tweets are protected",
        "this account's tweets are protected",
        "you're not authorized to see this",
        "not authorized to see"
    ]
    
    for indicator in complete_privacy_indicators:
        if indicator in page_content:
            print(f"[!] Detected complete privacy restriction: '{indicator}' found in page")
            print(f"[!] {username}'s following list is completely private or protected.")
            return []
    
    # Check if we're actually on the following page
    if f"/{username}/following" not in driver.current_url:
        print(f"[!] Not on following page. Current URL: {driver.current_url}")
        print(f"[!] May have been redirected due to privacy settings or login issues.")
        return []
    
    # Check for empty following list (but account is public)
    if "doesn't follow anyone yet" in page_content or "not following anyone" in page_content:
        print(f"[!] {username} doesn't appear to follow anyone yet.")
        return []
    
    print(f"[+] Page appears accessible, proceeding to collect following...")
    print(f"[!] Note: Private accounts (with lock icons) will be included - privacy status doesn't affect mutual following")
    return scroll_and_collect_users_with_dates(driver, "following")

def get_profile_pic(driver, username):
    """Get profile picture URL for a user - Firefox compatible with high quality"""
    url = f'https://x.com/{username}'
    print(f'     [!] Fetching high-quality profile pic from {url}')
    driver.get(url)
    
    try:
        # Wait for profile image to load - Firefox-compatible selectors
        selectors_to_try = [
            'img[src*="profile_images"]',
            '[data-testid="UserAvatar-Container"] img',
            'div[data-testid*="UserAvatar"] img',
            'img[alt*="profile"]',
            'img[src*="pbs.twimg.com"]',
            'div img[src*="twimg"]'
        ]
        
        img_element = None
        for selector in selectors_to_try:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                img_element = driver.find_element(By.CSS_SELECTOR, selector)
                if img_element:
                    src = img_element.get_attribute('src')
                    if src and ('profile_images' in src or 'pbs.twimg.com' in src):
                        break
            except (TimeoutException, NoSuchElementException):
                continue
        
        if img_element:
            pic_url = img_element.get_attribute('src')
            
            if pic_url and ('profile_images' in pic_url or 'pbs.twimg.com' in pic_url):
                # Get the highest quality version by removing all size restrictions
                high_quality_url = re.sub(r'_\d+x\d+', '', pic_url)
                high_quality_url = re.sub(r'_normal', '', high_quality_url)
                high_quality_url = re.sub(r'_bigger', '', high_quality_url)
                high_quality_url = re.sub(r'_mini', '', high_quality_url)
                
                print(f'     [>] High-quality URL: {high_quality_url}')
                return high_quality_url
        else:
            # Fallback: try to find any profile image in the page source
            print(f'     [!] Trying page source fallback...')
            page_source = driver.page_source
            profile_img_pattern = r'https://pbs\.twimg\.com/profile_images/[^"]*'
            matches = re.findall(profile_img_pattern, page_source)
            if matches:
                pic_url = matches[0]
                # Remove size restrictions for highest quality
                high_quality_url = re.sub(r'_\d+x\d+', '', pic_url)
                high_quality_url = re.sub(r'_normal', '', high_quality_url)
                high_quality_url = re.sub(r'_bigger', '', high_quality_url)
                high_quality_url = re.sub(r'_mini', '', high_quality_url)
                
                print(f'     [>] High-quality URL (fallback): {high_quality_url}')
                return high_quality_url
            
    except Exception as e:
        print(f"     [-] Could not find profile picture for {username}: {e}")
    
    return None

def download_image(url, filepath, username):
    """Download high-quality image from URL to filepath with retry logic and enhanced debugging"""
    try:
        print(f'     [!] Starting download for {username}')
        print(f'     [!] URL: {url}')
        print(f'     [!] Filepath: {filepath}')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        print(f'     [!] Downloading high-quality image from: {url}')
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Try downloading with different quality fallbacks
        urls_to_try = [
            url,  # Original (highest quality)
            re.sub(r'https://pbs\.twimg\.com/profile_images/([^/]+)/', r'https://pbs.twimg.com/profile_images/\1/', url) + '_400x400',  # 400x400 fallback
            re.sub(r'https://pbs\.twimg\.com/profile_images/([^/]+)/', r'https://pbs.twimg.com/profile_images/\1/', url) + '_200x200'   # 200x200 fallback
        ]
        
        for attempt, download_url in enumerate(urls_to_try, 1):
            try:
                print(f'     [!] Attempt {attempt}: {download_url}')
                response = requests.get(download_url, headers=headers, timeout=30)
                print(f'     [!] Response status: {response.status_code}')
                print(f'     [!] Content-Type: {response.headers.get("content-type", "unknown")}')
                response.raise_for_status()
                
                # Check if we got a valid image
                content_type = response.headers.get('content-type', '')
                if content_type.startswith('image/'):
                    print(f'     [!] Writing {len(response.content)} bytes to {filepath}')
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    # Verify file was created and has content
                    if os.path.exists(filepath):
                        file_size = os.path.getsize(filepath)
                        print(f'     [+] File created successfully: {file_size} bytes')
                        return True
                    else:
                        print(f'     [!?] File was not created at {filepath}')
                else:
                    print(f'     [!?] Attempt {attempt}: Not an image (content-type: {content_type})')
                    
            except requests.RequestException as e:
                print(f'     [!?] Attempt {attempt} failed: {e}')
                continue
            except Exception as e:
                print(f'     [!?] Attempt {attempt} unexpected error: {e}')
                continue
        
        print(f'     [-] All download attempts failed for {username}')
        return False
        
    except Exception as e:
        print(f"     [-] Failed to download image for {username}: {e}")
        import traceback
        print(f"     [!] Traceback: {traceback.format_exc()}")
        return False

def main():
    print("=== X/Twitter Mutual Following Scraper ===")
    print("(Finds people you follow who also follow you back)")
    print(f"Target username: {USERNAME}")
    print(f"Download directory: {DOWNLOAD_DIR}")
    print(f"Download choice: {download_choice}")
    print("=" * 50)
    
    driver = setup_driver()
    
    try:
        # Step 1: Login to Twitter
        if not login_to_twitter(driver):
            print("[-] Login failed. Cannot proceed without authentication.")
            return
        
        print('\n1. Fetching following (people you follow)...')
        following_data = get_following(driver, USERNAME)
        print(f'Found {len(following_data)} people you follow.')
        
        if not following_data:
            print("[-] No following found. This could mean:")
            print("   - The account is private")
            print("   - You're not logged in properly")
            print("   - The username is incorrect")
            print("[!] Retrying login and following fetch...")
            if login_to_twitter(driver):
                following_data = get_following(driver, USERNAME)
            if not following_data:
                print("[!?] Still no following data after retry. Exiting.")
                return
        
        # Separate mutuals and non-mutuals
        mutual_following_data = [user for user in following_data if user.get('is_mutual', False)]
        non_mutual_following_data = [user for user in following_data if not user.get('is_mutual', False)]
        
        print(f'\n[+] Found {len(mutual_following_data)} mutual follows (they follow you back)')
        print(f'[+] Found {len(non_mutual_following_data)} non-mutual follows (they don\'t follow you back)')
        print(f'[+] Total: {len(following_data)} people you follow')
        
        # Determine which data to process based on user choice
        if download_choice == '1':
            # Only mutuals
            users_to_process = mutual_following_data
            list_type = "mutual following (people who follow you back)"
            print(f'\n[!] Processing only mutual follows...')
        elif download_choice == '2':
            # All users
            users_to_process = following_data
            list_type = "all following"
            print(f'\n[!] Processing all following (both mutual and non-mutual)...')
        elif download_choice == '3':
            # Both - we'll save separate JSON files
            users_to_process = following_data
            list_type = "all following"
            print(f'\n[!] Processing all following (will create separate files for mutuals and non-mutuals)...')
        else:
            # Default to mutuals only
            users_to_process = mutual_following_data
            list_type = "mutual following (people who follow you back)"
            print(f'\n[!] Invalid choice, defaulting to mutual follows only...')
        
        if len(users_to_process) == 0:
            print("[-] No users to process based on your selection.")
            return
        
        print(f'\n2. Downloading profile pictures for {len(users_to_process)} users...')
        
        for idx, user_data in enumerate(users_to_process):
            username = user_data['username']
            display_name = user_data.get('displayName', '')
            display_info = f" ({display_name})" if display_name else ""
            mutual_status = "MUTUAL" if user_data.get('is_mutual', False) else "NON-MUTUAL"
            
            print(f"\n[!] Processing @{username}{display_info} [{mutual_status}] ({idx + 1}/{len(users_to_process)})")
            
            pic_url = user_data.get('profile_pic_url')
            pic_downloaded = False
            temp_filename = None
            
            # If we don't have a profile pic URL from the cell, fetch it from their profile
            if not pic_url or not is_valid_twitter_profile_url(pic_url, verbose=False):
                print(f'     [!] Fetching profile pic from profile page...')
                pic_url = get_profile_pic(driver, username)
                # Update the user_data with the fetched URL
                user_data['profile_pic_url'] = pic_url
                # Add delay after visiting profile page
                time.sleep(PROFILE_CHECK_DELAY)
            else:
                print(f'     [+] Using profile pic URL from following page')
            
            # Download the profile picture
            if pic_url:
                # Create filename with temporary numbering (we'll rename later)
                temp_filename = f'temp_{idx:03d}_@{username}.jpg'
                temp_filepath = os.path.join(DOWNLOAD_DIR, temp_filename)
                
                pic_downloaded = download_image(pic_url, temp_filepath, username)
                if pic_downloaded:
                    print(f'     [+] Profile picture downloaded to {temp_filename}')
                else:
                    print(f'     [-] Failed to download profile picture')
            else:
                print(f'     [-] Could not find profile picture URL')
            
            # Update user_data with download status
            user_data['pic_downloaded'] = pic_downloaded
            user_data['temp_filename'] = temp_filename if pic_downloaded else None
        
        
        # Sort by position: Twitter shows newest first at position 0
        # We want oldest first (#1 = oldest follow), so we need to reverse the order
        users_to_process.sort(key=lambda x: x['position'], reverse=True)
        
        print(f'\n[+] Found {len(users_to_process)} {list_type} (ordered by when you followed them, oldest to newest):')
        print("-" * 60)
        
        # Create a list to store results with timestamps
        results = []
        
        # Now rename the temp files to proper numbered filenames and create results
        for idx, user_data in enumerate(users_to_process, 1):
            username = user_data['username']
            display_name = user_data.get('displayName', '')
            display_info = f" ({display_name})" if display_name else ""
            mutual_tag = " [MUTUAL]" if user_data.get('is_mutual', False) else ""
            print(f'{idx:3d}. @{username}{display_info}{mutual_tag} (position #{user_data["position"] + 1})')
            
            pic_downloaded = user_data.get('pic_downloaded', False)
            temp_filename = user_data.get('temp_filename')
            
            if pic_downloaded and temp_filename:
                # Rename temp file to proper numbered filename
                old_filepath = os.path.join(DOWNLOAD_DIR, temp_filename)
                new_filename = f'{idx:03d}_@{username}.jpg'
                new_filepath = os.path.join(DOWNLOAD_DIR, new_filename)
                
                try:
                    os.rename(old_filepath, new_filepath)
                    print(f'     [+] Profile picture saved as {new_filename}')
                except Exception as e:
                    print(f'     [!] Error renaming file: {e}')
                    new_filename = temp_filename  # Keep temp name if rename fails
            else:
                new_filename = None
                print(f'     [-] No profile picture available')
            
            # Store result
            results.append({
                'number': idx,
                'displayName': display_name,
                'username': username,
                'url': user_data.get('url', f'https://x.com/{username}'),
                'follow_date': user_data['follow_date'],
                'original_position': user_data['position'],
                'is_mutual': user_data.get('is_mutual', False),
                'profile_pic_url': user_data.get('profile_pic_url'),
                'pic_downloaded': pic_downloaded,
                'filename': new_filename
            })
        
        print(f'\n=== COLLECTION SUMMARY ===')
        print(f'[+] Total people you follow found: {len(following_data)}')
        print(f'[+] Mutual follows: {len(mutual_following_data)}')
        print(f'[+] Non-mutual follows: {len(non_mutual_following_data)}')
        
        print(f'\n=== SUMMARY ===')
        print(f'[+] Total processed: {len(users_to_process)}')
        successful_downloads = sum(1 for r in results if r['pic_downloaded'])
        print(f'[+] Profile pictures downloaded: {successful_downloads}/{len(users_to_process)}')
        print(f'[!] Images saved to: {DOWNLOAD_DIR}/')
        print(f'[!] Filename format: 001_@username.jpg, 002_@username.jpg, etc.')
        print(f'[!] Ordered from: oldest person you followed (#1) to newest person you followed (#{len(users_to_process)})')
        
        # Save results to JSON file(s) based on user choice
        if download_choice == '3':
            # Save separate files for mutuals and non-mutuals
            mutual_results = [r for r in results if r['is_mutual']]
            non_mutual_results = [r for r in results if not r['is_mutual']]
            
            # Mutuals JSON
            mutuals_json = {
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'target_username': USERNAME,
                'list_type': 'mutual following',
                'totalMutuals': len(mutual_results),
                'mutuals': mutual_results
            }
            
            # Non-mutuals JSON
            non_mutuals_json = {
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'target_username': USERNAME,
                'list_type': 'non-mutual following',
                'totalNonMutuals': len(non_mutual_results),
                'nonMutuals': non_mutual_results
            }
            
            # Combined JSON
            combined_json = {
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'target_username': USERNAME,
                'totalMutuals': len(mutual_results),
                'totalNonMutuals': len(non_mutual_results),
                'mutuals': mutual_results,
                'nonMutuals': non_mutual_results
            }
            
            try:
                with open('mutuals_only.json', 'w', encoding='utf-8') as f:
                    json.dump(mutuals_json, f, indent=2, ensure_ascii=False)
                print(f'[!] Mutuals saved to: mutuals_only.json')
                
                with open('non_mutuals_only.json', 'w', encoding='utf-8') as f:
                    json.dump(non_mutuals_json, f, indent=2, ensure_ascii=False)
                print(f'[!] Non-mutuals saved to: non_mutuals_only.json')
                
                with open('x_twitter_mutual_data.json', 'w', encoding='utf-8') as f:
                    json.dump(combined_json, f, indent=2, ensure_ascii=False)
                print(f'[!] Combined data saved to: x_twitter_mutual_data.json')
            except Exception as e:
                print(f'[!?] Failed to save JSON files: {e}')
        else:
            # Single JSON file
            json_data = {
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'target_username': USERNAME,
                'list_type': list_type,
                'total_results': len(users_to_process),
                'total_following': len(following_data),
                'totalMutuals': len(mutual_following_data),
                'totalNonMutuals': len(non_mutual_following_data),
                'successful_downloads': successful_downloads,
                'results': results
            }
            
            try:
                with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                print(f'[!] Results saved to: {JSON_OUTPUT_FILE}')
            except Exception as e:
                print(f'[!?] Failed to save JSON file: {e}')
        
    except KeyboardInterrupt:
        print("\n[!?] Process interrupted by user.")
    except Exception as e:
        print(f"[-] An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[!] Closing browser...")
        
        # Cleanup temporary profile if it exists
        temp_profile = getattr(driver, 'temp_profile_path', None)
        
        driver.quit()
        
        if temp_profile and temp_profile.exists():
            print("[!] Cleaning up temporary profile...")
            try:
                shutil.rmtree(temp_profile, ignore_errors=True)
                print("[+] Temporary profile cleaned up")
            except Exception as e:
                print(f"[!] Could not remove temporary profile: {e}")
        
        print("[+] Done!")

if __name__ == '__main__':
    main()
