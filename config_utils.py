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
    """Singleton pattern để chỉ install driver 1 lần duy nhất."""
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
    
    # --- PERFORMANCE OPTIMIZATION FLAGS ---
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu") 
    
    # Block images (Speed boost)
    options.add_argument("--blink-settings=imagesEnabled=false") 
    
    # Block CSS & Fonts to speed up rendering (Optional - nếu làm vỡ giao diện login thì bỏ dòng này)
    # options.add_argument("--blink-settings=imagesEnabled=false,cssEnabled=false")
    
    # Disable extensions & bars
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    
    # Disk I/O Optimizations (Giảm ghi ổ cứng -> Nhanh hơn)
    options.add_argument("--disable-application-cache")
    options.add_argument("--disk-cache-size=0") 
    options.add_argument("--disable-logging") # Giảm log rác của Chrome
    options.add_argument("--log-level=3")
    
    # Load strategy: 'eager' là nhanh nhất (không đợi sub-resources như ảnh/css tải xong)
    options.page_load_strategy = 'eager'
    
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    try:
        service = Service(_get_chromedriver_path())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set timeout thấp hơn để fail fast nếu mạng lag (Tùy chỉnh nếu mạng chậm)
        driver.set_page_load_timeout(30) 
        driver.set_script_timeout(30)
        return driver
    except Exception as e:
        print(f"Error creating driver: {e}")
        raise e

def parse_cookie_string(cookie_str):
    """
    Convert raw cookie string: "datr=abc; ds_user_id=123;..." 
    to List Dictionary for Selenium.
    Keeps error handling intact.
    """
    cookies = []
    try:
        if not cookie_str:
            return cookies
            
        # Split key=value pairs by ;
        pairs = cookie_str.split(';')
        for pair in pairs:
            if '=' in pair:
                # split(..., 1) đảm bảo chỉ cắt ở dấu = đầu tiên
                key, value = pair.strip().split('=', 1)
                cookies.append({
                    'name': key, 
                    'value': value, 
                    'domain': '.instagram.com', 
                    'path': '/'
                })
    except Exception as e:
        print(f"Cookie parse error: {e}")
    return cookies

# --- OPTIMIZED WAIT FUNCTIONS ---
# Logic: Giảm poll time từ 0.2s -> 0.1s để phản hồi nhanh hơn.
# Logic: Giữ nguyên try-except pass để đảm bảo tính ổn định như code cũ.

def wait_dom_ready(driver, timeout=10, poll=0.1):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return True
        except Exception:
            pass
        time.sleep(poll)
    return False

def wait_element(driver, by, value, timeout=10, poll=0.1, visible=True):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            elements = driver.find_elements(by, value)
            for el in elements:
                # Logic cũ: nếu visible=True thì phải check is_displayed
                # nếu visible=False thì chỉ cần tìm thấy là được
                if not visible or el.is_displayed():
                    return el
        except Exception:
            pass
        time.sleep(poll)
    return None

def wait_and_click(driver, by, value, timeout=10, poll=0.1):
    # Reuse wait_element logic
    el = wait_element(driver, by, value, timeout=timeout, poll=poll, visible=True)
    if not el:
        return False
    try:
        el.click()
        return True
    except Exception:
        # Fallback JS Click
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False

def wait_and_send_keys(driver, by, value, keys, timeout=10, poll=0.1, clear_first=True):
    # Visible = False cũng được, miễn là tương tác được (SendKeys cần element interactable)
    # Tuy nhiên code cũ để visible=False, ta giữ nguyên để tránh lỗi logic tìm ẩn
    el = wait_element(driver, by, value, timeout=timeout, poll=poll, visible=True) 
    
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