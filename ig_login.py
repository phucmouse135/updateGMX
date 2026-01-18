# ig_login.py
import time
from selenium.webdriver.common.by import By
from config_utils import parse_cookie_string, wait_dom_ready, wait_element

def _handle_cookie_consent(driver):
    """
    Xử lý popup 'Allow cookies' của Instagram (Châu Âu/Mỹ thường gặp).
    Ưu tiên bấm 'Allow all' hoặc 'Decline optional' để đóng popup.
    """
    try:
        # Các từ khóa thường gặp trên nút
        xpaths = [
            "//button[contains(text(), 'Allow all cookies')]",
            "//button[contains(text(), 'Decline optional cookies')]",
            "//button[contains(text(), 'Only allow essential cookies')]",
            "//button[contains(text(), 'Chấp nhận tất cả')]",
            "//button[contains(text(), 'Từ chối cookie')]"
        ]
        
        for xp in xpaths:
            btns = driver.find_elements(By.XPATH, xp)
            for btn in btns:
                if btn.is_displayed():
                    print("   [IG] Detected Cookie Popup -> Clicking...")
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1) # Chờ popup tắt
                    return True
    except:
        pass
    return False

def login_instagram_via_cookie(driver, cookie_raw_string):
    """
    Login IG via cookie.
    Return: True (Success) / False (Fail)
    """
    print("   [IG] Loading Cookies...")
    
    # 1. Load Homepage
    driver.get("https://www.instagram.com/")
    
    # --- XỬ LÝ POPUP COOKIE NGAY LÚC ĐẦU ---
    _handle_cookie_consent(driver)
    
    # 2. Add Cookies
    cookies = parse_cookie_string(cookie_raw_string)
    if not cookies:
        print("   [IG] Error: No cookies parsed.")
    
    for c in cookies:
        try: driver.add_cookie(c)
        except: pass
        
    # 3. Refresh
    driver.refresh()
    
    # --- XỬ LÝ POPUP COOKIE LẦN 2 (SAU KHI REFRESH) ---
    # Đôi khi refresh xong nó mới hiện lại
    _handle_cookie_consent(driver)
    
    # 4. Detection Loop (Fast)
    end_time = time.time() + 10
    
    SEL_PASS = "input[name='password'], input[type='password']"
    SEL_ERROR = "//*[contains(text(), 'Use another profile') or contains(text(), 'Chuyển tài khoản khác')]"
    SEL_HOME  = "svg[aria-label='Home'], svg[aria-label='Trang chủ'], svg[aria-label='Search']"
    
    while time.time() < end_time:
        # Check Success
        if len(driver.find_elements(By.CSS_SELECTOR, SEL_HOME)) > 0:
            break
        # Check Fail
        if len(driver.find_elements(By.CSS_SELECTOR, SEL_PASS)) > 0:
            break
        if len(driver.find_elements(By.XPATH, SEL_ERROR)) > 0:
            break
        
        # Check Popup again while waiting
        _handle_cookie_consent(driver)
        
        time.sleep(0.5)

    # 5. Handle Notification Popups (Not Now)
    try:
        popups = driver.find_elements(By.XPATH, "//button[contains(text(), 'Not Now') or contains(text(), 'Lúc khác')]")
        for btn in popups:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
    except: pass

    # 6. Validate
    has_pass = len(driver.find_elements(By.CSS_SELECTOR, SEL_PASS)) > 0
    has_home = len(driver.find_elements(By.CSS_SELECTOR, SEL_HOME)) > 0
    
    if has_pass and not has_home:
        print("   [IG] Login FAIL (Cookie dead).")
        return False
        
    if has_home:
        print("   [IG] Login SUCCESS!")
        return True
        
    # Checkpoint case
    print("   [IG] Warning: Home not found (Possible Checkpoint).")
    return True