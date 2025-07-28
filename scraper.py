import os
import requests
import json
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
CHECK_MUTUALS = input("Do you want me to check if they are mutuals? (y/n): ").strip().lower() in ['y', 'yes', '1', 'true']
DOWNLOAD_PICS = input("Do you want to download profile pictures? (y/n): ").strip().lower() in ['y', 'yes', '1', 'true']
DOWNLOAD_DIR = 'profile_pics'
SCROLL_PAUSE_TIME = 2      # Time to wait between scrolls (optimized for speed)
PROFILE_CHECK_DELAY = 5    # Delay between profile visits to avoid 429 errors (reduced for better speed)
JSON_OUTPUT_FILE = 'mutual_following.json'  # JSON output file

# --- SETUP ---
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def setup_driver():
    """Setup Firefox WebDriver with optimal settings for Twitter scraping"""
    print("Setting up Firefox WebDriver...")
    
    try:
        # Use WebDriverManager to automatically download and manage GeckoDriver
        service = Service(GeckoDriverManager().install())
        print("GeckoDriver installed/updated successfully")
    except Exception as e:
        print(f"WebDriverManager failed, trying default GeckoDriver: {e}")
        service = None
    
    firefox_options = Options()
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--disable-dev-shm-usage')
    firefox_options.set_preference('dom.webdriver.enabled', False)
    firefox_options.set_preference('useAutomationExtension', False)
    firefox_options.set_preference('general.useragent.override', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0')
    
    # Silence Firefox errors and warnings
    firefox_options.add_argument('--disable-logging')
    firefox_options.add_argument('--log-level=3')  # Only show fatal errors
    firefox_options.add_argument('--silent')
    firefox_options.set_preference('media.volume_scale', '0.0')  # Mute audio
    firefox_options.set_preference('browser.startup.homepage', 'about:blank')
    firefox_options.set_preference('startup.homepage_welcome_url', 'about:blank')
    firefox_options.set_preference('startup.homepage_override_url', 'about:blank')
    
    # Privacy and security settings
    firefox_options.set_preference('privacy.trackingprotection.enabled', False)
    firefox_options.set_preference('browser.safebrowsing.enabled', False)
    firefox_options.set_preference('browser.safebrowsing.malware.enabled', False)
    
    # Performance optimizations
    firefox_options.set_preference('browser.tabs.animate', False)
    firefox_options.set_preference('browser.fullscreen.animateUp', 0)
    firefox_options.set_preference('browser.cache.disk.enable', False)
    firefox_options.set_preference('browser.cache.memory.enable', False)
    firefox_options.set_preference('browser.sessionstore.max_tabs_undo', 0)
    
    # Don't run headless so user can see and interact with the browser
    # firefox_options.add_argument('--headless')  # Commented out for manual login
    
    try:
        if service:
            driver = webdriver.Firefox(service=service, options=firefox_options)
        else:
            driver = webdriver.Firefox(options=firefox_options)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print("Firefox browser launched successfully")
        return driver
        
    except Exception as e:
        print(f"Failed to start Firefox WebDriver: {e}")
        print("\nTROUBLESHOOTING:")
        print("1. Make sure Mozilla Firefox browser is installed")
        print("2. Try updating Firefox to the latest version")
        print("3. Restart your computer and try again")
        print("4. If you don't have Firefox, download it from: https://www.mozilla.org/firefox/")
        raise

def login_to_twitter(driver):
    """Navigate to Twitter login and wait for user to log in manually"""
    print("\nLOGIN REQUIRED")
    print("=" * 50)
    print("X/Twitter requires you to be logged in to view following lists.")
    print("The browser will now open to X/Twitter login page.")
    print("Please log in manually and then the script will automatically continue.")
    print("=" * 50)
    
    # Navigate to login page
    driver.get('https://x.com/login')
    
    # Wait for user to log in automatically by checking for login success
    print("\nPlease log in to X/Twitter in the browser window...")
    print("Script will automatically continue once login is detected...")
    
    # Wait for login to complete by checking for logged-in elements
    max_wait_time = 300  # 5 minutes maximum wait
    check_interval = 10   # Check every 10 seconds (less frequent to avoid triggering security)
    
    for attempt in range(0, max_wait_time, check_interval):
        try:
            # Check current page for login indicators WITHOUT navigating away
            current_url = driver.current_url.lower()
            print(f"Current URL: {current_url}")
            
            # If we're no longer on login page, check if we're logged in
            if 'login' not in current_url:
                try:
                    # Check for logged-in elements on current page
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
                                print("Login successful!")
                                return True
                        except TimeoutException:
                            continue
                    
                    # If no elements found but not on login page, try going to home once
                    print("Not on login page but no login elements found. Trying home page...")
                    driver.get('https://x.com/home')
                    time.sleep(5)
                    
                    # Check again after going to home
                    for selector in logged_in_elements:
                        try:
                            element = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            if element:
                                print("Login successful!")
                                return True
                        except TimeoutException:
                            continue
                            
                except Exception as e:
                    print(f"Error checking login elements: {e}")
            
            # Still on login page or not logged in, wait and check again
            if attempt < max_wait_time - check_interval:
                print(f"Still waiting for login... ({attempt + check_interval}s elapsed)")
                time.sleep(check_interval)
            
        except Exception as e:
            print(f"Error checking login status: {e}")
            time.sleep(check_interval)
            continue
    
    print("Login timeout. Please make sure you're logged in and try again.")
    return False

def scroll_and_collect_users_with_dates(driver, page_type="followers"):
    """Scroll through a list and collect user handles with their follow dates - complete single pass"""
    users_data = []
    last_height = driver.execute_script("return document.body.scrollHeight")
    no_new_users_count = 0
    stagnant_height_count = 0
    scroll_count = 0
    
    print(f"Starting comprehensive single-pass scroll through {page_type} list...")
    
    while True:
        scroll_count += 1
        print(f"Scroll #{scroll_count} - Current users: {len(users_data)}")
        
        # Scroll down
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        
        # Collect users from current view with multiple detection strategies
        old_count = len(users_data)
        try:
            # Strategy 1: Look for UserCell elements (most reliable)
            user_cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
            print(f"Found {len(user_cells)} UserCell elements on current view")
            
            for cell in user_cells:
                try:
                    # Check if this cell contains "Follows you" indicator (for mutual detection)
                    follows_you_elements = cell.find_elements(By.XPATH, ".//*[contains(text(), 'Follows you')]")
                    is_mutual = len(follows_you_elements) > 0
                    
                    # Also check for other status indicators
                    has_following = len(cell.find_elements(By.XPATH, ".//*[contains(text(), 'Following') or contains(text(), 'Follows you')]")) > 0
                    
                    # Find username link - try multiple approaches
                    username_links = cell.find_elements(By.CSS_SELECTOR, 'a[href^="/"]')
                    for username_link in username_links:
                        href = username_link.get_attribute('href')
                        
                        if href and is_valid_user_link(href):
                            username = extract_username_from_url(href)
                            
                            if username and is_valid_username(username):
                                # Check if we already have this user
                                if not any(user['username'] == username for user in users_data):
                                    # Try to find follow date or any timestamp info
                                    follow_date = extract_follow_date(cell, len(users_data))
                                    
                                    # Try to extract profile picture URL from the cell (non-verbose for speed)
                                    profile_pic_url = extract_profile_pic_from_cell(cell, verbose=False)
                                    
                                    users_data.append({
                                        'username': username,
                                        'follow_date': follow_date,
                                        'position': len(users_data),
                                        'has_status_indicator': has_following,
                                        'is_mutual': is_mutual,
                                        'profile_pic_url': profile_pic_url
                                    })
                                    pic_status = "[PIC]" if profile_pic_url else "[NO PIC]"
                                    mutual_status = "[MUTUAL]" if is_mutual else "[ONE-WAY]"
                                    print(f"Added user: {username} (position {len(users_data)}) - {mutual_status} - {pic_status}")
                                    break  # Found a valid user in this cell, move to next cell
                                
                except Exception as e:
                    continue
                    
            # Strategy 2: Fallback detection methods
            if len(users_data) == old_count:
                print("UserCell method found no new users, trying fallback methods...")
                
                # Try alternative selectors
                selectors = [
                    '[data-testid="cellInnerDiv"] a[href^="/"]',
                    'div[dir="ltr"] a[href^="/"]',
                    'a[role="link"][href^="/"]',
                    'a[href*="/"][role="link"]',
                    'a[href^="/"]'
                ]
                
                for selector in selectors:
                    user_links = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Trying selector '{selector}' - found {len(user_links)} links")
                    
                    for link in user_links:
                        try:
                            href = link.get_attribute('href')
                            if href and is_valid_user_link(href):
                                username = extract_username_from_url(href)
                                if username and is_valid_username(username):
                                    if not any(user['username'] == username for user in users_data):
                                        # Try to find the parent cell for profile pic extraction and mutual status
                                        try:
                                            parent_cell = link.find_element(By.XPATH, "./ancestor::*[@data-testid='UserCell']")
                                            profile_pic_url = extract_profile_pic_from_cell(parent_cell, verbose=False)
                                            # Check for mutual status in parent cell
                                            follows_you_elements = parent_cell.find_elements(By.XPATH, ".//*[contains(text(), 'Follows you')]")
                                            is_mutual = len(follows_you_elements) > 0
                                        except:
                                            profile_pic_url = None
                                            is_mutual = False
                                            
                                        users_data.append({
                                            'username': username,
                                            'follow_date': f"position_{len(users_data)}",
                                            'position': len(users_data),
                                            'has_status_indicator': False,
                                            'is_mutual': is_mutual,
                                            'profile_pic_url': profile_pic_url
                                        })
                                        pic_status = "[PIC]" if profile_pic_url else "[NO PIC]"
                                        mutual_status = "[MUTUAL]" if is_mutual else "[ONE-WAY]"
                                        print(f"Added user (fallback): {username} - {mutual_status} - {pic_status}")
                                        break
                        except Exception:
                            continue
                    
                    if len(users_data) > old_count:
                        break  # Found some users with this selector
                        
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error collecting users: {e}")
        
        # Check if we found new users - stop immediately if no new users found
        new_count = len(users_data)
        if new_count == old_count:
            no_new_users_count += 1
            print(f"No new users found in this scroll - stopping collection")
            print(f"Completed scroll with {scroll_count} total scrolls")
            break
        else:
            no_new_users_count = 0
            
        print(f"Collected {len(users_data)} users so far (scroll #{scroll_count})")
        
        # Check if we've reached the bottom by comparing page height
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            stagnant_height_count += 1
            print(f"Page height unchanged - likely reached end of list")
            print(f"Completed scroll with {scroll_count} total scrolls")
            break
        else:
            stagnant_height_count = 0
        last_height = new_height
        
        # Additional check: try to detect "end of list" indicators
        try:
            page_source = driver.page_source.lower()
            end_indicators = [
                "you've reached the end",
                "no more to show",
                "no more results",
                "end of list",
                "nothing more to load",
                "end of timeline"
            ]
            
            for indicator in end_indicators:
                if indicator in page_source:
                    print(f"Detected end-of-list indicator: '{indicator}'")
                    print(f"Completed scroll with {scroll_count} total scrolls")
                    return users_data
                    
        except Exception:
            pass
        
        # Safety valve: if we've scrolled excessively (100+ times), something might be wrong
        if scroll_count > 100:
            print(f"Safety stop at {scroll_count} scrolls - this seems excessive")
            print(f"Completed scroll with {scroll_count} total scrolls")
            break
    
    print(f"Completed single-pass scroll with {scroll_count} total scrolls")
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

def is_valid_twitter_profile_url(url, verbose=True):
    """Check if a URL is a valid Twitter profile image URL"""
    if not url:
        return False
    
    # Must be a proper HTTP/HTTPS URL
    if not url.startswith(('http://', 'https://')):
        if verbose:
            print(f"     Invalid URL scheme: {url}")
        return False
    
    # Must be from Twitter's CDN
    if 'pbs.twimg.com' not in url or 'profile_images' not in url:
        if verbose:
            print(f"     Not a Twitter profile image URL: {url}")
        return False
    
    # Should not be a data URL or other invalid format
    if url.startswith('data:'):
        if verbose:
            print(f"     Data URL not supported: {url[:50]}...")
        return False
    
    return True

def extract_profile_pic_from_cell(cell, verbose=True):
    """Extract profile picture URL from a UserCell element - Firefox compatible with optional debugging"""
    try:
        if verbose:
            print(f"     Searching for profile pic in UserCell...")
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
                    print(f"     Trying selector {selector_idx}: {selector}")
                images = cell.find_elements(By.CSS_SELECTOR, selector)
                if verbose:
                    print(f"     Found {len(images)} images with this selector")
                
                for img_idx, img in enumerate(images, 1):
                    try:
                        src = img.get_attribute('src')
                        if verbose:
                            print(f"     Image {img_idx} src: {src}")
                        
                        if src and is_valid_twitter_profile_url(src, verbose=verbose):
                            # Convert to highest quality version (original size)
                            pic_url = re.sub(r'_\d+x\d+', '_400x400', src)  # Start with 400x400
                            pic_url = re.sub(r'_normal', '_400x400', pic_url)  # Replace _normal with _400x400
                            pic_url = re.sub(r'_bigger', '_400x400', pic_url)  # Replace _bigger with _400x400
                            pic_url = re.sub(r'_mini', '_400x400', pic_url)   # Replace _mini with _400x400
                            
                            # Try to get even higher quality by removing size restrictions entirely
                            high_quality_url = re.sub(r'_400x400', '', pic_url)
                            
                            if verbose:
                                print(f"     Found valid profile pic: {high_quality_url}")
                            return high_quality_url
                    except Exception as e:
                        if verbose:
                            print(f"     Error processing image {img_idx}: {e}")
                        continue
            except Exception as e:
                if verbose:
                    print(f"     Error with selector {selector_idx}: {e}")
                continue
        
        if verbose:
            print(f"     No profile picture found in UserCell")
    except Exception as e:
        if verbose:
            print(f"     Error in extract_profile_pic_from_cell: {e}")
    return None

def get_following(driver, username):
    """Get all following for a given username"""
    url = f'https://x.com/{username}/following'
    print(f"Navigating to following page: {url}")
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
            print("Not logged in or session expired. Please log in again.")
            return []
            
    except TimeoutException:
        print("Timeout waiting for following page to load")
        return []
    
    time.sleep(5)  # Additional wait for dynamic content
    
    print(f"Checking page content for user: {username}")
    
    # Check if the following list is completely inaccessible (but allow private accounts in list)
    page_content = driver.page_source.lower()
    
    # Debug: Print current URL and check for common error indicators
    print(f"Current URL: {driver.current_url}")
    
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
            print(f"Detected complete privacy restriction: '{indicator}' found in page")
            print(f"{username}'s following list is completely private or protected.")
            return []
    
    # Check if we're actually on the following page
    if f"/{username}/following" not in driver.current_url:
        print(f"Not on following page. Current URL: {driver.current_url}")
        print(f"May have been redirected due to privacy settings or login issues.")
        return []
    
    # Check for empty following list (but account is public)
    if "doesn't follow anyone yet" in page_content or "not following anyone" in page_content:
        print(f"{username} doesn't appear to follow anyone yet.")
        return []
    
    print(f"Page appears accessible, proceeding to collect following...")
    print(f"Note: Private accounts (with lock icons) will be included - privacy status doesn't affect mutual following")
    return scroll_and_collect_users_with_dates(driver, "following")

def get_profile_pic(driver, username):
    """Get profile picture URL for a user - Firefox compatible with high quality"""
    url = f'https://x.com/{username}'
    print(f'     Fetching high-quality profile pic from {url}')
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
                
                print(f'     High-quality URL: {high_quality_url}')
                return high_quality_url
        else:
            # Fallback: try to find any profile image in the page source
            print(f'     Trying page source fallback...')
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
                
                print(f'     High-quality URL (fallback): {high_quality_url}')
                return high_quality_url
            
    except Exception as e:
        print(f"     Could not find profile picture for {username}: {e}")
    
    return None

def download_image(url, filepath, username):
    """Download high-quality image from URL to filepath with retry logic and enhanced debugging"""
    try:
        print(f'     Starting download for {username}')
        print(f'     URL: {url}')
        print(f'     Filepath: {filepath}')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        print(f'     Downloading high-quality image from: {url}')
        
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
                print(f'     Attempt {attempt}: {download_url}')
                response = requests.get(download_url, headers=headers, timeout=30)
                print(f'     Response status: {response.status_code}')
                print(f'     Content-Type: {response.headers.get("content-type", "unknown")}')
                response.raise_for_status()
                
                # Check if we got a valid image
                content_type = response.headers.get('content-type', '')
                if content_type.startswith('image/'):
                    print(f'     Writing {len(response.content)} bytes to {filepath}')
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    # Verify file was created and has content
                    if os.path.exists(filepath):
                        file_size = os.path.getsize(filepath)
                        print(f'     File created successfully: {file_size} bytes')
                        return True
                    else:
                        print(f'     File was not created at {filepath}')
                else:
                    print(f'     Attempt {attempt}: Not an image (content-type: {content_type})')
                    
            except requests.RequestException as e:
                print(f'     Attempt {attempt} failed: {e}')
                continue
            except Exception as e:
                print(f'     Attempt {attempt} unexpected error: {e}')
                continue
        
        print(f'     All download attempts failed for {username}')
        return False
        
    except Exception as e:
        print(f"     Failed to download image for {username}: {e}")
        import traceback
        print(f"     Traceback: {traceback.format_exc()}")
        return False

def main():
    print("=== X/Twitter Mutual Following Scraper ===")
    print("(Finds people you follow who also follow you back)")
    print(f"Target username: {USERNAME}")
    print(f"Download directory: {DOWNLOAD_DIR}")
    print("=" * 50)
    
    driver = setup_driver()
    
    try:
        # Step 1: Login to Twitter
        if not login_to_twitter(driver):
            print("Login failed. Cannot proceed without authentication.")
            return
        
        print('\n1. Fetching following (people you follow)...')
        following_data = get_following(driver, USERNAME)
        print(f'Found {len(following_data)} people you follow.')
        
        if not following_data:
            print("No following found. This could mean:")
            print("   - The account is private")
            print("   - You're not logged in properly")
            print("   - The username is incorrect")
            print("Retrying login and following fetch...")
            if login_to_twitter(driver):
                following_data = get_following(driver, USERNAME)
            if not following_data:
                print("Still no following data after retry. Exiting.")
                return
        
        if not CHECK_MUTUALS:
            print('\nSkipping mutual check as requested.')
            print(f'Found {len(following_data)} people you follow (no mutual filtering)')
            
            # Create simplified results (numbered from newest to oldest)
            simplified_results = []
            for idx, user_data in enumerate(following_data, 1):
                username = user_data['username']
                # Reverse the numbering: newest person you followed gets #1
                reversed_number = len(following_data) - idx + 1
                print(f'{reversed_number:3d}. @{username} (position {user_data["position"] + 1})')
                
                simplified_results.append(f"{reversed_number}. @{username}")
            
            # Save results to JSON file with simplified format
            json_data = {
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'target_username': USERNAME,
                'list_type': 'following (all people you follow)',
                'total_results': len(following_data),
                'mutual_check_performed': False,
                'results': simplified_results
            }
            
            try:
                with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                print(f'\nResults saved to: {JSON_OUTPUT_FILE}')
            except Exception as e:
                print(f'Failed to save JSON file: {e}')
            
            print(f'\n=== SUMMARY ===')
            print(f'Total people you follow: {len(following_data)}')
            print(f'Mutual check: SKIPPED (as requested)')
            print(f'Profile picture downloading: DISABLED')
            print(f'Only following data collected')
            return
        
        print(f'\n2. Processing mutual following data (profile picture downloading {"enabled" if DOWNLOAD_PICS else "disabled"})...')
        
        # Filter for mutual followers from the data we already collected
        mutual_following_data = []
        
        for user_data in following_data:
            username = user_data['username']
            is_mutual = user_data.get('is_mutual', False)
            
            if is_mutual:
                print(f"[MUTUAL] @{username} follows you back")
                
                # Handle profile picture downloading if enabled
                pic_url = user_data.get('profile_pic_url')
                pic_downloaded = False
                filename = None
                
                if DOWNLOAD_PICS and pic_url:
                    print(f'     Downloading profile picture...')
                    filename = f'{len(mutual_following_data) + 1:03d}_@{username}.jpg'
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    
                    pic_downloaded = download_image(pic_url, filepath, username)
                    if pic_downloaded:
                        print(f'     Profile picture saved as {filename}')
                    else:
                        print(f'     Failed to download profile picture')
                        filename = None
                elif DOWNLOAD_PICS:
                    print(f'     No profile picture URL available')
                else:
                    print(f'     Profile picture downloading is disabled')
                
                mutual_following_data.append({
                    'username': user_data['username'],
                    'follow_date': user_data['follow_date'],
                    'position': user_data['position'],
                    'source': 'mutual_following',
                    'profile_pic_url': pic_url,
                    'pic_downloaded': pic_downloaded,
                    'filename': filename
                })
            else:
                print(f"[ONE-WAY] @{username} doesn't follow you back")
        
        # Sort by position in REVERSE order (since Twitter shows newest first, we want oldest first)
        # Position 0 = newest person you followed, so reverse to get oldest first
        mutual_following_data.sort(key=lambda x: x['position'], reverse=True)
        
        list_type = "mutual following (people who follow you back)"
        print(f'\nFound {len(mutual_following_data)} {list_type} (numbered from newest to oldest):')
        print("-" * 60)
        
        # Create a list to store simplified results
        simplified_results = []
        
        # Create simplified results (numbered from newest to oldest)
        for idx, user_data in enumerate(mutual_following_data, 1):
            username = user_data['username']
            # Reverse the numbering: newest mutual gets #1
            reversed_number = len(mutual_following_data) - idx + 1
            print(f'{reversed_number:3d}. @{username} (you followed them #{user_data["position"] + 1})')
            
            # Get file info
            pic_downloaded = user_data.get('pic_downloaded', False)
            filename = user_data.get('filename')
            
            if DOWNLOAD_PICS and pic_downloaded and filename:
                print(f'     Profile picture saved as {filename}')
            elif DOWNLOAD_PICS:
                print(f'     No profile picture available')
            else:
                print(f'     Profile picture downloading was disabled')
            
            # Store simplified result with reversed numbering
            simplified_results.append(f"{reversed_number}. @{username} [Mutual]")
        
        print(f'\n=== SUMMARY ===')
        list_type = "mutual following (people who follow you back)"
        print(f'Total {list_type}: {len(mutual_following_data)}')
        successful_downloads = sum(1 for user_data in mutual_following_data if user_data.get('pic_downloaded', False))
        
        if DOWNLOAD_PICS:
            print(f'Profile pictures downloaded: {successful_downloads}/{len(mutual_following_data)}')
            print(f'Images saved to: {DOWNLOAD_DIR}/')
            print(f'Filename format: 001_@username.jpg, 002_@username.jpg, etc.')
        else:
            print(f'Profile picture downloading: DISABLED')
            print(f'No images downloaded (feature disabled)')
            print(f'Only mutual following data collected')
        
        print(f'Ordered from: newest person you followed (#1) to oldest person you followed (#{len(mutual_following_data)})')
        print(f'Note: These are people YOU follow who also follow YOU back (mutual following)')
        
        # Save results to JSON file with simplified format
        json_data = {
            'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'target_username': USERNAME,
            'list_type': list_type,
            'total_results': len(mutual_following_data),
            'mutual_check_performed': True,
            'results': simplified_results
        }
        
        try:
            with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            print(f'Results saved to: {JSON_OUTPUT_FILE}')
        except Exception as e:
            print(f'Failed to save JSON file: {e}')
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nClosing browser...")
        driver.quit()
        print("Done!")

if __name__ == '__main__':
    main()
