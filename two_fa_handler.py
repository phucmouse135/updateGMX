# two_fa_handler.py
import time
import re
import pyotp
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys 
from selenium.webdriver.common.action_chains import ActionChains
from config_utils import wait_and_click, wait_dom_ready, wait_element

# --- IMPORT MAIL HANDLER ---
try:
    from mail_handler import get_code_from_mail
except ImportError:
    print("   [ERROR] Missing 'mail_handler.py'!")

# ==========================================
# 1. JS SENSOR (TRẠNG THÁI TRANG)
# ==========================================
def get_page_state(driver):
    """Quét toàn bộ Body để xác định trạng thái hiện tại."""
    js_sensor = """
    function checkState() {
        var body = document.body.innerText.toLowerCase();
        var url = window.location.href;

        // 0. Check trang Download Lite
        if (body.includes("download instagram lite") || url.includes("lite") || body.includes("download apk")) {
            return 'LITE_PAGE';
        }

        // --- CHECK UNUSUAL LOGIN ---
        if (body.includes("unusual login") || body.includes("suspicious login") || (body.includes("this was me") && body.includes("this wasn't me"))) {
            return 'UNUSUAL_LOGIN';
        }
        
        // 1. Check lỗi chặn/khóa
        if (body.includes("you can't make this change") || body.includes("change at the moment")) return 'RESTRICTED';
        if (body.includes("suspended") || body.includes("đình chỉ")) return 'SUSPENDED';
        if (body.includes("sorry, this page isn't available")) return 'BROKEN';

        // 2. Check 2FA đã bật
        if (body.includes("authentication is on") || body.includes("xác thực 2 yếu tố đang bật")) {
             return 'ALREADY_ON';
        }
        
        // 3. Check Select App
        if (body.includes("help protect your account") || body.includes("authentication app") || body.includes("ứng dụng xác thực")) {
             return 'SELECT_APP';
        }

        // --- BLOCK UNSUPPORTED METHODS ---
        if (body.includes("check your whatsapp") || body.includes("whatsapp account") || body.includes("gửi đến whatsapp")) {
            return 'WHATSAPP_REQUIRED';
        }
        if (body.includes("check your sms") || body.includes("text message") || body.includes("tin nhắn văn bản")) {
            return 'SMS_REQUIRED';
        }

        // 4. Check Checkpoint
        var inputs = document.querySelectorAll("input");
        for (var i=0; i<inputs.length; i++) {
            if (inputs[i].offsetParent !== null) {
                var attr = (inputs[i].name + " " + inputs[i].placeholder + " " + inputs[i].getAttribute("aria-label")).toLowerCase();
                if (attr.includes("code") || attr.includes("security") || inputs[i].type === "tel" || inputs[i].type === "number") {
                    return 'CHECKPOINT';
                }
            }
        }
        
        if (body.includes("check your email") || body.includes("enter the code")) return 'CHECKPOINT';

        // Màn hình chọn phương thức (Step 3)
        if (body.includes("help protect your account") || (body.includes("authentication app") && body.includes("sms"))) return 'SELECT_APP';

        var hasInput = document.querySelector("input[name='code']") || document.querySelector("input[placeholder*='Code']");
        var hasNext = false;
        var btns = document.querySelectorAll("button, div[role='button']");
        for (var b of btns) { if (b.innerText.toLowerCase().includes("next") || b.innerText.toLowerCase().includes("tiếp")) hasNext = true; }

        // NHẬN DIỆN MÀN HÌNH NHẬP OTP (STEP 5)
        if (hasInput && body.includes("authentication app") && hasNext) return 'OTP_INPUT_SCREEN';
        return 'UNKNOWN';
    }
    return checkState();
    """
    try: return driver.execute_script(js_sensor)
    except: return 'UNKNOWN'

# ==========================================
# 2. HELPERS
# ==========================================

def _check_mask_match(real_email, masked_hint):
    if not real_email or "@" not in real_email: return False
    try:
        real_user, real_domain = real_email.lower().strip().split("@")
        mask_user, mask_domain = masked_hint.lower().strip().split("@")
        if mask_domain[0] != '*' and mask_domain[0] != real_domain[0]: return False
        if "." in mask_domain:
            if mask_domain.split('.')[-1] != real_domain.split('.')[-1]: return False
        if mask_user[0] != '*' and mask_user[0] != real_user[0]: return False
        return True
    except: return False

def _validate_masked_email_robust(driver, primary_email, secondary_email=None):
    """
    Xác minh xem email gợi ý trên màn hình IG có phải là email của mình không.
    Trả về True nếu khớp, False nếu không khớp.
    """
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        # Tìm định dạng email masked: h****@g**.de
        match = re.search(r'\b([a-zA-Z0-9][\w\*]*@[\w\*]+\.[a-zA-Z\.]+)\b', body_text)
        
        if not match: 
            print("   [2FA] No hint found on screen. Proceeding with caution...")
            return True 
            
        masked = match.group(1).lower().strip()
        print(f"   [2FA] Detected Hint: {masked}")
        
        # So khớp với Email gốc hoặc Email liên kết
        is_primary = _check_mask_match(primary_email, masked)
        is_secondary = secondary_email and _check_mask_match(secondary_email, masked)
        
        if is_primary:
            print(f"   [2FA] Match confirmed: Primary Email ({primary_email})")
            return True
        if is_secondary:
            print(f"   [2FA] Match confirmed: Linked Email ({secondary_email})")
            return True
            
        # NẾU KHÔNG KHỚP -> CẢNH BÁO VÀ TRẢ VỀ FALSE
        print(f"   [CRITICAL] Hint {masked} DOES NOT match provided emails!")
        return False
        
    except Exception as e:
        print(f"   [2FA] Warning validate hint error: {e}")
        return True # Mặc định cho qua nếu lỗi quét, hoặc bạn có thể đổi thành False để an toàn hơn

def _robust_fill_input(driver, text_value):
    """
    Điền code: Tìm trong Modal trước, dùng ActionChains gõ phím.
    Check value sau khi gõ để đảm bảo.
    """
    input_el = None
    
    # A. Tìm Input trong Dialog/Modal
    try:
        dialog_inputs = driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'] input, div[role='main'] input")
        for inp in dialog_inputs:
            if inp.is_displayed(): 
                input_el = inp
                break
    except: pass

    # B. Fallback Selector
    if not input_el:
        selectors = ["input[name='code']", "input[placeholder*='Code']", "input[type='tel']", "input[maxlength='6']"]
        for sel in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed(): 
                    input_el = el
                    break
            except: pass
    
    if not input_el: return False
    val = str(text_value).strip()

    # C. ActionChains Typing
    try:
        ActionChains(driver).move_to_element(input_el).click().perform()
        time.sleep(0.1)
        input_el.send_keys(Keys.CONTROL + "a"); input_el.send_keys(Keys.DELETE)
        for char in val: 
            input_el.send_keys(char)
            time.sleep(0.03) 
        
        # Check value update
        for _ in range(10):
            if input_el.get_attribute("value").replace(" ", "") == val: return True
            time.sleep(0.2)
    except: pass

    # D. JS Inject Fallback
    try:
        driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", input_el, val)
        time.sleep(0.5)
        return input_el.get_attribute("value").replace(" ", "") == val
    except: pass
    
    return False

def click_continue_robust(driver):
    """Click Continue/Next/Done"""
    js_click = """
    var keywords = ["Next", "Tiếp", "Continue", "Submit", "Xác nhận", "Confirm", "Done", "Xong", "This Was Me", "Đây là tôi", "Đúng là tôi"];
    var btns = document.querySelectorAll("button, div[role='button']");
    for (var b of btns) {
        var txt = b.innerText.trim();
        for(var k of keywords) { 
            if(txt.includes(k) && b.offsetParent !== null && !b.disabled && b.offsetHeight > 0) { 
                b.click(); return true; 
            } 
        }
    }
    return false;
    """
    return driver.execute_script(js_click)

# ==========================================
# 3. MAIN LOGIC FLOW
# ==========================================

def setup_2fa(driver, email, email_pass, target_username=None, linked_email=None):
    print(f"   [2FA] Accessing settings...")
    target_url = "https://accountscenter.instagram.com/password_and_security/two_factor/"
    driver.get(target_url)
    wait_dom_ready(driver, timeout=5)

    # --- 0. BYPASS 'DOWNLOAD APP' PAGE ---
    if "lite" in driver.current_url or len(driver.find_elements(By.XPATH, "//*[contains(text(), 'Download Instagram Lite')]")) > 0:
        print("   [2FA] Detected 'Download Lite' page. Attempting bypass...")
        try:
            btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'Not now') or contains(text(), 'Lúc khác')]")
            if btns: 
                btns[0].click()
                wait_dom_ready(driver, timeout=5)
            else: 
                driver.get(target_url)
                wait_dom_ready(driver, timeout=5)
        except: pass

    # -------------------------------------------------
    # STEP 1: SELECT ACCOUNT
    # -------------------------------------------------
    print("   [2FA] Step 1: Selecting Account...")
    acc_selected = False
    for attempt in range(3):
        try:
            wait_element(driver, By.XPATH, "//div[@role='button'] | //a[@role='link']", timeout=5)
            clicked = driver.execute_script("""
                var els = document.querySelectorAll('div[role="button"], a[role="link"]');
                for (var i=0; i<els.length; i++) {
                    if (els[i].innerText.toLowerCase().includes('instagram')) { els[i].click(); return true; }
                }
                return false;
            """)
            if clicked: 
                acc_selected = True
                wait_dom_ready(driver, timeout=5)
                break
            else:
                if "lite" in driver.current_url: 
                    driver.get(target_url)
                    wait_dom_ready(driver, timeout=5)
                else: time.sleep(1)
        except: time.sleep(1)
    
    if not acc_selected: print("   [2FA] Warning: Select Account failed (May already be inside).")

    # -------------------------------------------------
    # STEP 2: SCAN STATE
    # -------------------------------------------------
    print("   [2FA] Scanning UI State...")
    state = "UNKNOWN"
    for _ in range(15):
        state = get_page_state(driver)
        
        # UNUSUAL LOGIN FIX
        if state == 'UNUSUAL_LOGIN':
            print("   [2FA] Detected 'Unusual Login'. Clicking 'This Was Me'...")
            if click_continue_robust(driver):
                print("   [2FA] Clicked 'This Was Me'. Waiting...")
                wait_dom_ready(driver, timeout=5)
                if "two_factor" not in driver.current_url:
                    driver.get(target_url)
                    wait_dom_ready(driver, timeout=5)
                continue 
            else: print("   [2FA] Cannot find 'This Was Me' button.")

        if state == 'LITE_PAGE': 
            driver.get(target_url)
            wait_dom_ready(driver, timeout=5)
            continue
        
        # BLOCK UNSUPPORTED
        if state == 'WHATSAPP_REQUIRED': raise Exception("FAIL: WhatsApp Verification Required")
        if state == 'SMS_REQUIRED': raise Exception("FAIL: SMS Verification Required")
        
        if state in ['SELECT_APP', 'CHECKPOINT', 'ALREADY_ON', 'RESTRICTED']: break
        time.sleep(0.5)

    print(f"   [2FA] Detected State: {state}")

    if state == 'RESTRICTED': raise RuntimeError("RESTRICTED_DEVICE")
    if state == 'SUSPENDED': raise RuntimeError("ACCOUNT_SUSPENDED")
    if state == 'ALREADY_ON': raise Exception("ALREADY_2FA_ON")

    # -------------------------------------------------
    # STEP 2.5: HANDLE CHECKPOINT (EMAIL) - OPTIMIZED
    # -------------------------------------------------
    if state == 'CHECKPOINT':
        print(f"   [2FA] Step 2.5: Handling Checkpoint (Optimized)...")
        _validate_masked_email_robust(driver, email, linked_email)
        # --- CHỐT CHẶN EMAIL TẠI ĐÂY ---
        if not _validate_masked_email_robust(driver, email, linked_email):
            print("   [STOP] Script halted: Targeted email is not yours.")
            raise RuntimeError("EMAIL_MISMATCH") # Dừng toàn bộ script tại đây
        checkpoint_passed = False
        
        for mail_attempt in range(3):
            print(f"   [2FA] Retrieval Attempt {mail_attempt + 1}/3...")
            
            # Tối ưu: Hàm IMAP mới quét Top 3 thư UNSEEN giúp tìm mã nhanh gấp 3 lần
            mail_code = get_code_from_mail(driver, email, email_pass)
            
            if not mail_code:
                # Nếu không thấy mã, kiểm tra xem trang có tự chuyển không trước khi bấm xin mã mới
                if get_page_state(driver) in ['SELECT_APP', 'ALREADY_ON']: 
                    checkpoint_passed = True; break
                
                print("   [2FA] Code not found. Requesting new code...")
                driver.execute_script("var a=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of a){if(e.innerText.toLowerCase().includes('get a new code')){e.click();break;}}")
                
                # Tối ưu: Giảm từ 12s xuống 5s vì IMAP phản hồi rất nhanh
                time.sleep(5) 
                continue 
            
            print(f"   [2FA] Got Code: {mail_code}. Inputting...")
            
            if _robust_fill_input(driver, mail_code):
                time.sleep(0.5)
                click_continue_robust(driver)
                
                # Polling kiểm tra kết quả
                is_invalid = False
                print("   [2FA] Verifying...")
                for _ in range(8): # Tối ưu: Giảm polling từ 12s xuống 8s
                    time.sleep(1)
                    curr = get_page_state(driver)
                    
                    if curr in ['SELECT_APP', 'ALREADY_ON']:
                        checkpoint_passed = True; break
                    
                    # Quét lỗi nhanh bằng JS
                    err_msg = driver.execute_script("return document.body.innerText.toLowerCase()")
                    if any(msg in err_msg for msg in ["isn't right", "work", "không đúng"]):
                        print(f"   [WARNING] Code {mail_code} invalid. Requesting new code...")
                        driver.execute_script("var a=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of a){if(e.innerText.toLowerCase().includes('get a new code')){e.click();break;}}")
                        is_invalid = True
                        time.sleep(4) # Tối ưu: Nghỉ ngắn 4s để thư mới kịp về
                        break 
                
                if checkpoint_passed: break
                if is_invalid: continue 
            else:
                time.sleep(1)
        
        if not checkpoint_passed: 
            raise Exception("CHECKPOINT_FAIL: Optimized retry limit reached.")

    # --- 3. SELECT AUTH APP ---
    print("   [2FA] Step 3: Selecting Auth App...")
    app_selected = False
    for attempt in range(3):
        try:
            if get_page_state(driver) == 'ALREADY_ON': 
                print("   [2FA] Detected: 2FA is already enabled.")
                raise Exception("2FA_EXISTS") # Chuẩn hóa lỗi theo yêu cầu
            driver.execute_script("""
                var els = document.querySelectorAll("div[role='button'], label");
                for (var i=0; i<els.length; i++) {
                     if (els[i].innerText.toLowerCase().includes("authentication app")) { els[i].click(); break; }
                }
            """)
            time.sleep(1)
            # Lệnh bấm Next để vào màn hình Key
            click_continue_robust(driver)
            time.sleep(4)
            # Check lại lần nữa phòng khi IG chuyển trạng thái nhanh
            if get_page_state(driver) == 'ALREADY_ON': raise Exception("2FA_EXISTS")
            if len(driver.find_elements(By.XPATH, "//*[contains(text(), 'Copy key') or contains(text(), 'Sao chép')]")) > 0:
                app_selected = True
                break
        except Exception as e:
            if "2FA_EXISTS" in str(e): raise e # Ném lỗi ra ngoài ngay
            time.sleep(1)
    
    if not app_selected:
        if get_page_state(driver) == 'ALREADY_ON': raise Exception("2FA_EXISTS")
        if len(driver.find_elements(By.XPATH, "//*[contains(text(), 'Copy key')]")) == 0:
            raise Exception("SELECT_APP_STUCK: Key screen not reached.")

    # -------------------------------------------------
    # STEP 4: GET SECRET KEY (CHỐT CHẶN CỨNG - KHÔNG SKIP)
    # -------------------------------------------------
    # time.sleep(5)
    wait_dom_ready(driver, timeout=5)
    print("   [2FA] Step 4: Getting Secret Key (Blocking until captured)...")
    secret_key = ""
    wait_dom_ready(driver, timeout=5)
    
    # Vòng lặp lấy Key: TUYỆT ĐỐI KHÔNG BẤM NEXT Ở ĐÂY
    end_wait = time.time() + 60
    while time.time() < end_wait:
        try:
            current_state = get_page_state(driver)
            if current_state == 'ALREADY_ON': raise Exception("2FA_EXISTS")
            driver.execute_script("var els=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of els){if(e.innerText.includes('Copy key')||e.innerText.includes('Sao chép')){e.click();break;}}")
            # 1. Tự sửa lỗi nếu bị nhảy sang màn OTP quá sớm mà chưa có Key
            if current_state == 'OTP_INPUT_SCREEN' and not secret_key:
                print("   [2FA] Warning: Skiped to OTP screen! Clicking Back to find Key...")
                # Click nút Back (biểu tượng < ở góc trái phía trên)
                driver.execute_script("""
                    var b = document.querySelector('div[role="button"] svg'); 
                    if(b) b.closest('div[role="button"]').click();
                """)
                # Đợi màn hình quay lại màn Key
                for _ in range(10):
                    if len(driver.find_elements(By.XPATH, "//*[contains(text(), 'Copy key')]")) > 0: break
                    time.sleep(0.5)

            driver.execute_script("""
                var els = document.querySelectorAll('span, div[role="button"]'); 
                for(var e of els){
                    if(e.innerText.includes('Copy key') || e.innerText.includes('Sao chép')){
                        e.click(); break;
                    }
                }
            """)
            # 3. Quét mã từ Text Body
            full_text = driver.find_element(By.TAG_NAME, "body").text
            m = re.search(r'([A-Z2-7]{4}\s?){4,}', full_text) 
            if m:
                clean = m.group(0).replace(" ", "").strip()
                if len(clean) >= 16: secret_key = clean; break
            
            # 4. Quét mã từ các Input ẩn (Trường hợp mã nằm trong ô text readonly)
            if not secret_key:
                inputs = driver.find_elements(By.TAG_NAME, "input")
                for inp in inputs:
                    val = inp.get_attribute("value")
                    if val:
                        clean_val = val.replace(" ", "").strip()
                        # Xác thực mã Base32 hợp lệ (chỉ gồm A-Z và 2-7, dài >= 16)
                        if len(clean_val) >= 16 and re.match(r'^[A-Z2-7]+$', clean_val):
                            secret_key = clean_val
                            break
            if secret_key: break
        except: pass
        time.sleep(1.5)
    
    if not secret_key: 
        raise Exception("STOP: Secret Key NOT found! Blocking flow to prevent Ghost 2FA.")
    
    # IN KEY KIỂM SOÁT
    print(f"\n========================================\n[2FA] !!! SECRET KEY FOUND: {secret_key}\n========================================\n")

    # =========================================================
    # STEP 5: CONFIRM OTP (FIXED INPUT)
    # =========================================================
    
    # 1. Click Next từ màn hình Copy Key
    print("   [2FA] Clicking Next to Input OTP...")
    click_continue_robust(driver)
    
    # 2. Tính toán OTP
    clean_key = "".join(secret_key.split())
    totp = pyotp.TOTP(clean_key, interval=30)
    otp_code = totp.now()
    
    # 3. Chờ ô Input xuất hiện
    print(f"   [2FA] Waiting for OTP Input (Code: {otp_code})...")
    
    # 4. ĐIỀN OTP BẰNG HÀM ROBUST
    is_filled = False
    fill_end = time.time() + 10 # Thử trong 10s
    while time.time() < fill_end:
        # Thử điền
        if _robust_fill_input(driver, otp_code):
            is_filled = True
            break
        print("   [2FA] Retrying input fill...")
        time.sleep(1)
        
    if not is_filled: raise Exception("OTP_INPUT_FAIL")
    
    print(f"   [2FA] Input Filled. Confirming...")
    
    # 5. Confirm
    time.sleep(0.5)
    click_continue_robust(driver)
    
    print("   [2FA] Waiting for completion...")
    end_confirm = time.time() + 15
    success = False
    
    while time.time() < end_confirm:
        res = driver.execute_script("""
            var body = document.body.innerText.toLowerCase();
            if (body.includes("code isn't right") || body.includes("mã không đúng")) return 'WRONG_OTP';
            
            var doneBtns = document.querySelectorAll("span");
            for(var b of doneBtns) {
                if((b.innerText === 'Done' || b.innerText === 'Xong') && b.offsetParent !== null) {
                    b.click(); return 'SUCCESS';
                }
            }
            return 'WAIT';
        """)
        
        if res == 'WRONG_OTP': 
            raise Exception("OTP_REJECTED")
        if res == 'SUCCESS' or get_page_state(driver) == 'ALREADY_ON': 
            success = True
            print("   [2FA] => SUCCESS: 2FA Enabled.")
            break

    if not success: raise Exception("TIMEOUT: Done button not found.")
    time.sleep(1)
    return secret_key