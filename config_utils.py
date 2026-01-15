# config_utils.py
import time
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

_CHROMEDRIVER_PATH = None
_CHROMEDRIVER_LOCK = threading.Lock()

def _get_chromedriver_path():
    global _CHROMEDRIVER_PATH
    if _CHROMEDRIVER_PATH:
        return _CHROMEDRIVER_PATH
    with _CHROMEDRIVER_LOCK:
        if not _CHROMEDRIVER_PATH:
            _CHROMEDRIVER_PATH = ChromeDriverManager().install()
    return _CHROMEDRIVER_PATH

def ensure_chromedriver():
    return _get_chromedriver_path()

def get_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new") 
    
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu") # Disable GPU acceleration to save resources
    options.add_argument("--blink-settings=imagesEnabled=false") # BLOCK IMAGES (Huge speed boost)
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    
    options.page_load_strategy = 'eager'
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(_get_chromedriver_path()), options=options)
    driver.set_page_load_timeout(20)
    return driver

def parse_cookie_string(cookie_str):
    """
    Convert raw cookie string: "datr=abc; ds_user_id=123;..." 
    to List Dictionary for Selenium
    """
    cookies = []
    try:
        # Split key=value pairs by ;
        pairs = cookie_str.split(';')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                cookies.append({
                    'name': key, 
                    'value': value, 
                    'domain': '.instagram.com', # Important: set domain for IG
                    'path': '/'
                })
    except Exception as e:
        print(f"Cookie parse error: {e}")
    return cookies

def wait_dom_ready(driver, timeout=10, poll=0.2):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return True
        except Exception:
            pass
        time.sleep(poll)
    return False

def wait_element(driver, by, value, timeout=10, poll=0.2, visible=True):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            elements = driver.find_elements(by, value)
            for el in elements:
                if not visible or el.is_displayed():
                    return el
        except Exception:
            pass
        time.sleep(poll)
    return None

def wait_and_click(driver, by, value, timeout=10, poll=0.2):
    el = wait_element(driver, by, value, timeout=timeout, poll=poll, visible=True)
    if not el:
        return False
    try:
        el.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False

def wait_and_send_keys(driver, by, value, keys, timeout=10, poll=0.2, clear_first=True):
    el = wait_element(driver, by, value, timeout=timeout, poll=poll, visible=False)
    if not el:
        return False
    if clear_first:
        try:
            el.clear()
        except Exception:
            pass
    try:
        el.send_keys(keys)
        return True
    except Exception:
        return False
