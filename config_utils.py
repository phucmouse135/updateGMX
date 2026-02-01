# config_utils.py
from selenium.webdriver.common.action_chains import ActionChains
import threading
import time
import os
import shutil
import tempfile
import psutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

_CHROMEDRIVER_PATH = None
_CHROMEDRIVER_LOCK = threading.Lock()

def _get_chromedriver_path():
    """Singleton pattern để chỉ lấy path driver 1 lần duy nhất."""
    global _CHROMEDRIVER_PATH
    if _CHROMEDRIVER_PATH:
        return _CHROMEDRIVER_PATH
    with _CHROMEDRIVER_LOCK:
        if not _CHROMEDRIVER_PATH:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            chromedriver_path = os.path.join(current_dir, 'chromedriver.exe')
            if os.path.exists(chromedriver_path):
                _CHROMEDRIVER_PATH = chromedriver_path
            else:
                raise FileNotFoundError(f"chromedriver.exe not found at {chromedriver_path}")
    return _CHROMEDRIVER_PATH

def ensure_chromedriver():
    return _get_chromedriver_path()

class SafeWebDriver:
    def __init__(self, headless=True, window_rect=None):
        self.headless = headless
        self.window_rect = window_rect
        self.driver = None
        self.user_data_dir = None
        self.service = None

    def __enter__(self):
        """Khởi tạo Chrome với Profile cách ly."""
        # 1. Tạo thư mục tạm riêng biệt (Isolation)
        self.user_data_dir = tempfile.mkdtemp(prefix="ig_auto_")
        
        options = Options()
        # Gán profile vào thư mục tạm -> Chạy song song không xung đột
        options.add_argument(f"--user-data-dir={self.user_data_dir}")
        
        if self.headless:
            options.add_argument("--headless=new")
        
        if not self.headless and self.window_rect:
            x, y, w, h = self.window_rect
            options.add_argument(f"--window-position={x},{y}")
            options.add_argument(f"--window-size={w},{h}")
        elif not self.headless:
            options.add_argument("--start-maximized")
        
        # --- PERFORMANCE & OPTIMIZATION ---
        options.add_argument("--disable-notifications")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-default-apps")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Block images
        options.add_argument("--blink-settings=imagesEnabled=false")
        
        # Disk optimizations
        options.add_argument("--disable-application-cache")
        options.add_argument("--disk-cache-size=0")
        options.add_argument("--log-level=3")
        
        options.page_load_strategy = 'eager'
        
        # Fake User Agent Chrome 144
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36")
        
        try:
            self.service = Service(_get_chromedriver_path())
            self.driver = webdriver.Chrome(service=self.service, options=options)
            
            # Anti-detect script
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            
            self.driver.set_page_load_timeout(60) 
            self.driver.set_script_timeout(60)
            
            return self.driver
        except Exception as e:
            # Nếu khởi tạo lỗi, dọn dẹp ngay
            self._cleanup()
            raise e

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Tự động dọn dẹp khi thoát khỏi khối 'with'."""
        self._cleanup()

    def _cleanup(self):
        # 1. Quit Driver
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

        # 2. Force Kill Process (Nếu bị treo)
        if self.service and self.service.process:
            try:
                proc = psutil.Process(self.service.process.pid)
                for child in proc.children(recursive=True):
                    try: child.kill()
                    except: pass
                proc.kill()
            except (psutil.NoSuchProcess, Exception):
                pass

        # 3. Xóa thư mục Profile tạm (Giải phóng ổ cứng)
        if self.user_data_dir and os.path.exists(self.user_data_dir):
            try:
                # Chờ 1 chút để file unlock
                time.sleep(1)
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
            except Exception as e:
                print(f"[CLEANUP ERROR] {e}")

# Giữ lại hàm cũ để tương thích ngược (nếu cần), nhưng trỏ về SafeWebDriver
def get_driver(headless=True, window_rect=None):
    """Legacy wrapper, không khuyến khích dùng trực tiếp nếu muốn auto-cleanup tốt nhất."""
    wd = SafeWebDriver(headless, window_rect)
    return wd.__enter__()

# --- GIỮ NGUYÊN CÁC HÀM HELPER KHÁC (wait_element, v.v.) ---
def parse_cookie_string(cookie_str):
    cookies = []
    try:
        if not cookie_str: return cookies
        pairs = cookie_str.split(';')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                cookies.append({'name': key, 'value': value, 'domain': '.instagram.com', 'path': '/'})
    except: pass
    return cookies

def wait_dom_ready(driver, timeout=5, poll=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.execute_script("return document.readyState") == "complete": return True
        except: pass
        time.sleep(poll)
    return False

def wait_element(driver, by, value, timeout=10, poll=0.1, visible=True):
    end = time.time() + timeout
    while time.time() < end:
        try:
            els = driver.find_elements(by, value)
            for el in els:
                if not visible or (el.is_displayed() and el.is_enabled()): return el
        except: pass
        time.sleep(poll)
    return None

def wait_and_click(driver, by, value, timeout=10):
    el = wait_element(driver, by, value, timeout)
    if el:
        try: el.click(); return True
        except:
            try: driver.execute_script("arguments[0].click();", el); return True
            except: pass
    return False

def wait_and_send_keys(driver, by, value, keys, timeout=10):
    el = wait_element(driver, by, value, timeout)
    if el:
        try: el.clear(); el.send_keys(keys); return True
        except: pass
    return False