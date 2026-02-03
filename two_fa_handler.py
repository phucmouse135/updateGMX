# step4_2fa.py
import time
import re
import pyotp
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from config_utils import wait_dom_ready, wait_element, wait_and_click

# Import Mail Handler
from mail_handler_v2 import get_2fa_code_v2

class Instagram2FAStep:
    def __init__(self, driver):
        self.driver = driver
        self.target_url = "https://accountscenter.instagram.com/password_and_security/two_factor/"

    def _safe_element_action(self, action_func, max_retries=3, delay=0.5):
        """
        Helper to perform element actions with retry on StaleElementReferenceException.
        Ensures stability by re-locating elements if they become stale.
        """
        from selenium.common.exceptions import StaleElementReferenceException
        for attempt in range(max_retries):
            try:
                return action_func()
            except StaleElementReferenceException:
                if attempt < max_retries - 1:
                    print(f"   [Step 4] Element stale, retrying ({attempt+1}/{max_retries})...")
                    time.sleep(delay)
                else:
                    raise
        return False

    def _find_code_input(self):
        """
        Helper to find the code input element using JS.
        """
        return self.driver.execute_script("""
            var inputs = document.querySelectorAll('input');
            for (var inp of inputs) {
                if (inp.offsetParent !== null) {
                    var name = inp.name.toLowerCase();
                    var placeholder = inp.placeholder ? inp.placeholder.toLowerCase() : '';
                    var id = inp.id ? inp.id.toLowerCase() : '';
                    if (name === 'code' || placeholder.includes('code') || inp.type === 'tel' || inp.maxLength == 6 || id.startsWith('_r_') || (inp.type === 'text' && inp.autocomplete === 'off')) {
                        return inp;
                    }
                }
            }
            return null;
        """)

    def setup_2fa(self, gmx_user, gmx_pass, target_username, linked_mail=None):
        """
        Setup 2FA Flow - Logic gốc bảo toàn, thêm tối ưu chống treo.
        """
        try: 
            print(f"   [Step 4] Accessing settings...")
            print(f"   [Step 4] Starting 2FA Setup for {target_username}...")
            self.driver.get(self.target_url)
            wait_dom_ready(self.driver, timeout=5)

            # --- 0. BYPASS 'DOWNLOAD APP' PAGE ---
            self._bypass_lite_page()

            # -------------------------------------------------
            # STEP 1: SELECT ACCOUNT
            # -------------------------------------------------
            print(f"   [Step 4] Step 1: Selecting Account for {target_username}...")
            acc_selected = self._select_account_center_profile(target_username)
            if not acc_selected:
                raise Exception("STOP_FLOW_2FA: Account selection failed")

            # -------------------------------------------------
            # STEP 2: SCAN STATE & HANDLE EXCEPTIONS
            # -------------------------------------------------
            print("   [Step 4] Scanning UI State...")
            state = "UNKNOWN"
            
            # Quét 15 lần (Logic gốc)
            for _ in range(15):
                state = self._get_page_state()
                
                # UNUSUAL LOGIN FIX
                if state == 'UNUSUAL_LOGIN':
                    print("   [Step 4] Detected 'Unusual Login'. Clicking 'This Was Me'...")
                    if self._click_continue_robust():
                        print("   [Step 4] Clicked 'This Was Me'. Waiting...")
                        wait_dom_ready(self.driver, timeout=5)
                        if "two_factor" not in self.driver.current_url:
                            self.driver.get(self.target_url)
                            wait_dom_ready(self.driver, timeout=5)
                    continue 

                if state == 'LITE_PAGE': 
                    self.driver.get(self.target_url)
                    wait_dom_ready(self.driver, timeout=5)
                    continue
                
                # BLOCK UNSUPPORTED METHODS
                if state == 'WHATSAPP_REQUIRED': 
                    raise Exception("STOP_FLOW_2FA: WhatsApp Verification Required")
                if state == 'SMS_REQUIRED': 
                    raise Exception("STOP_FLOW_2FA: SMS Verification Required")
                if state == 'BROKEN': 
                    raise Exception("STOP_FLOW_2FA: Page Broken/Content Unavailable")
                
                # Thoát vòng lặp nếu trạng thái đã rõ ràng
                if state in ['SELECT_APP', 'CHECKPOINT', 'ALREADY_ON', 'RESTRICTED', 'OTP_INPUT_SCREEN']: 
                    break
                
                time.sleep(0.5)

            print(f"   [Step 4] Detected State: {state}")

            if state == 'RESTRICTED': 
                raise Exception("STOP_FLOW_2FA: RESTRICTED_DEVICE")
            if state == 'SUSPENDED': 
                raise Exception("STOP_FLOW_2FA: ACCOUNT_SUSPENDED")
            if state == 'ALREADY_ON': 
                print("   [Step 4] 2FA is already ON.")
                return "ALREADY_2FA_ON"

            # -------------------------------------------------
            # STEP 2.5: HANDLE CHECKPOINT (INTERNAL)
            # -------------------------------------------------
            if state == 'CHECKPOINT':
                print(f"   [Step 4] Step 2.5: Handling Internal Checkpoint...")
                if not self._validate_masked_email_robust(gmx_user, linked_mail):
                    print("   [STOP] Script halted: Targeted email is not yours.")
                    raise Exception("STOP_FLOW_2FA: EMAIL_MISMATCH") 
                time.sleep(1.5)
                result = self._solve_internal_checkpoint(gmx_user, gmx_pass, target_username)
                state = self._get_page_state()

            # -------------------------------------------------
            # STEP 3: SELECT AUTH APP
            # -------------------------------------------------
            print("   [Step 4] Step 3: Selecting Auth App...")
            self._select_auth_app_method(state)

            # -------------------------------------------------
            # STEP 4: GET SECRET KEY (CHỐT CHẶN CỨNG - KHÔNG SKIP)
            # -------------------------------------------------
            wait_dom_ready(self.driver, timeout=5)
            print("   [Step 4] Step 4: Getting Secret Key (Blocking until captured)...")
            time.sleep(5) 
            
            # [UPDATED] Hàm này đã được tối ưu để check Anti-Freeze
            secret_key = self._extract_secret_key(ig_username = target_username)
            
            def format_key_groups(key):
                key_nospaces = key.replace(" ", "")
                return " ".join([key_nospaces[i:i+4] for i in range(0, len(key_nospaces), 4)])

            secret_key_grouped = format_key_groups(secret_key)
            self.last_secret_key_raw = secret_key_grouped # Lưu lại cho GUI
            
            print(f"\n========================================\n[Step 4] !!! SECRET KEY FOUND: {secret_key_grouped}\n========================================\n")

            # Tính toán OTP ngay sau khi có secret key để tiết kiệm thời gian
            key_for_otp = secret_key.replace(" ","")
            totp = pyotp.TOTP(key_for_otp, interval=30)
            otp_code = totp.now()
            print(f"   [Step 4] Pre-generated OTP Code: {otp_code}")

            # Callback GUI
            if hasattr(self, 'on_secret_key_found') and callable(self.on_secret_key_found):
                try: self.on_secret_key_found(secret_key_grouped)
                except Exception as e: print(f"[Step 4] GUI callback error: {e}")

            # -------------------------------------------------
            # STEP 5: CONFIRM OTP (FIXED INPUT)
            # -------------------------------------------------
            print("   [Step 4] Clicking Next to Input OTP...")
            self._click_continue_robust()
            
            # Đảm bảo chắc chắn sang màn hình nhập OTP (giảm timeout xuống 5s, poll 0.5s)
            wait_end = time.time() + 5
            while time.time() < wait_end:
                if self._get_page_state() == 'OTP_INPUT_SCREEN':
                    print("   [Step 4] Confirmed: On OTP Input Screen.")
                    break
                time.sleep(0.5)
            else:
                print("   [Step 4] Warning: Not on OTP input screen yet, proceeding anyway.")
            
            print(f"   [Step 4] Using OTP Code: {otp_code}")
            
            is_filled = False
            fill_end = time.time() + 5  # Giảm timeout xuống 5s
            while time.time() < fill_end:
                if self._robust_fill_input(otp_code):
                    is_filled = True; break
                print("   [Step 4] Retrying input fill...")
                time.sleep(0.5)  # Poll nhanh hơn
                
            if not is_filled: 
                raise Exception("STOP_FLOW_2FA: OTP_INPUT_FAIL")
            
            print(f"   [Step 4] OTP Input Filled. Confirming...")
            time.sleep(0.3)  # Giảm wait xuống 0.3s
            self._click_continue_robust()
            
            # -------------------------------------------------
            # LOGIC RECOVERY (CONTENT NO LONGER AVAILABLE)
            # -------------------------------------------------
            time.sleep(2) # Chờ popup
            
            is_error_popup = self.driver.execute_script("""
                var body = document.body.innerText.toLowerCase();
                var keywords = ["content is no longer available", "không khả dụng", "không hiển thị được lúc này"];
                return keywords.some(k => body.includes(k));
            """)

            if is_error_popup:
                print("   [Step 4] ⚠️ CRITICAL: Error Pop-up detected! Initiating Recovery Flow...")
                
                # 1. RELOAD
                print("   [Recovery] Reloading page...")
                self.driver.refresh(); wait_dom_ready(self.driver, timeout=10); time.sleep(2)
                # 2. CLICK NEXT
                print("   [Recovery] Clicking Next/Continue...")
                self._click_continue_robust(); time.sleep(5)

                # 3. HANDOVER STEP 2
                print("   [Recovery] Handover to Step 2 Handler...")
                from step2_exceptions import InstagramExceptionStep
                step2_handler = InstagramExceptionStep(self.driver)
                current_status = step2_handler._check_verification_result()
                print(f"   [Recovery] Status detected: {current_status}")
                step2_handler.handle_status(current_status, target_username, gmx_user, gmx_pass, linked_mail, None)

                # 4. CLICK TO HOME
                print("   [Recovery] Finalizing: Clearing post-login screens...")
                max_final_clicks = 8
                for i in range(max_final_clicks):
                    curr_url = self.driver.current_url.lower()
                    try: body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except: body_text = ""

                    is_home = "instagram.com/" in curr_url and \
                            "/challenge/" not in curr_url and \
                            "/two_factor/" not in curr_url and \
                            any(k in body_text for k in ["search", "home", "reels", "direct", "posts"])
                    
                    if is_home:
                        print("   [Recovery] SUCCESS: Reached Instagram Home.")
                        break 
                    
                    clicked = self.driver.execute_script("""
                        var selectors = ["button", "div[role='button']", "span"];
                        var keywords = ["next", "tiếp", "continue", "submit", "xác nhận", "confirm", "done", "xong", "save", "lưu", "not now", "lúc khác"];
                        for (var sel of selectors) {
                            var btns = document.querySelectorAll(sel);
                            for (var b of btns) {
                                var txt = b.innerText.toLowerCase();
                                if (b.offsetParent !== null && keywords.some(k => txt.includes(k))) {
                                    b.click(); return true;
                                }
                            }
                        }
                        return false;
                    """)
                    if not clicked: time.sleep(1)
                    else: time.sleep(2)

                print("   [Recovery] Flow Completed. Returning Success immediately.")
                return secret_key 

            else:
                print("   [Step 4] No error pop-up detected. Continuing standard check...")
            
            # -------------------------------------------------
            # STANDARD CHECK (DONE BUTTON)
            # -------------------------------------------------
            print("   [Step 4] Waiting for completion...")
            end_confirm = time.time() + 60
            success = False
            
            while time.time() < end_confirm:
                res = self.driver.execute_script("""
                    var body = document.body.innerText.toLowerCase();
                    if (body.includes("code isn't right") || body.includes("mã không đúng")) return 'WRONG_OTP';
                    if (body.includes("this content is no longer available") || body.includes("không khả dụng")) return 'SUCCESS';
                    
                    var doneBtns = document.querySelectorAll("span, div[role='button']");
                    for(var b of doneBtns) {
                        if((b.innerText === 'Done' || b.innerText === 'Xong') && b.offsetParent !== null) {
                            b.click(); return 'SUCCESS';
                        }
                    }
                    if (body.includes("authentication is on")) return 'SUCCESS';
                    return 'WAIT';
                """)
                
                if res == 'WRONG_OTP': 
                    raise Exception("STOP_FLOW_2FA: OTP_REJECTED")
                if res == 'SUCCESS' or self._get_page_state() == 'ALREADY_ON': 
                    success = True
                    print("   [Step 4] => SUCCESS: 2FA Enabled.")
                    break
                time.sleep(1)

            if not success: 
                raise Exception("STOP_FLOW_2FA: TIMEOUT (Done button not found)")
            time.sleep(1)
            return secret_key
        except Exception as e: # <--- THÊM EXCEPT ĐỂ BẮT MỌI LỖI
            err_msg = str(e)
            print(f"   [Step 4] Error handled gracefully: {err_msg}")
            
            # Trả về nội dung lỗi để điền vào cột 2FA
            # Loại bỏ prefix "STOP_FLOW_2FA: " cho ngắn gọn nếu muốn
            clean_err = err_msg.replace("STOP_FLOW_2FA: ", "").strip()
            return f"ERROR_2FA: {clean_err}"

    # ==========================================
    # CORE HELPERS
    # ==========================================

    def _bypass_lite_page(self):
        if "lite" in self.driver.current_url or len(self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Download Instagram Lite')]")) > 0:
            print("   [Step 4] Detected 'Download Lite' page. Attempting bypass...")
            try:
                btns = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Not now') or contains(text(), 'Lúc khác')]")
                if btns: 
                    btns[0].click(); wait_dom_ready(self.driver, timeout=5)
                else: 
                    self.driver.get(self.target_url); wait_dom_ready(self.driver, timeout=5)
            except: pass

    def _select_account_center_profile(self, target_username):
        acc_selected = False
        for attempt in range(3):
            try:
                wait_element(self.driver, By.XPATH, "//div[@role='button'] | //a[@role='link']", timeout=5)
                clicked = self.driver.execute_script("""
                    var target = arguments[0].toLowerCase();
                    var els = document.querySelectorAll('div[role="button"], a[role="link"]');
                    // Ưu tiên chọn tài khoản có username chính xác
                    for (var i=0; i<els.length; i++) {
                        var txt = els[i].innerText.toLowerCase();
                        if (txt.includes(target) && txt.includes('instagram')) { 
                            els[i].click(); return true; 
                        }
                    }
                    // Fallback: Chọn bất kỳ tài khoản Instagram nào
                    for (var i=0; i<els.length; i++) {
                        if (els[i].innerText.toLowerCase().includes('instagram')) { 
                            els[i].click(); return true; 
                        }
                    }
                    return false;
                """, target_username)
                if clicked: 
                    acc_selected = True; wait_dom_ready(self.driver, timeout=5); break
                else: time.sleep(1)
            except: time.sleep(1)
        if not acc_selected: 
            print("   [Step 4] Warning: Select Account failed (May already be inside).")
            return False
        return acc_selected

    def _get_page_state(self):
        # [UPDATED] JS Sensor nhanh + check Content Unavailable
        js_sensor = """
        function checkState() {
            var body = document.body.innerText.toLowerCase();
            var url = window.location.href;

            if (body.includes("content is no longer available")) return 'BROKEN';
            if (body.includes("sorry, this page isn't available")) return 'BROKEN';

            if (body.includes("download instagram lite") || url.includes("lite") || body.includes("download apk")) return 'LITE_PAGE';

            if (body.includes("unusual login") || body.includes("suspicious login")) return 'UNUSUAL_LOGIN';
            
            if (body.includes("you can't make this change")) return 'RESTRICTED';
            if (body.includes("suspended") || body.includes("đình chỉ")) return 'SUSPENDED';

            if (body.includes("authentication is on") || body.includes("xác thực 2 yếu tố đang bật")) return 'ALREADY_ON';
            
            if (body.includes("help protect your account") || body.includes("authentication app")) return 'SELECT_APP';

            if (body.includes("check your whatsapp")) return 'WHATSAPP_REQUIRED';
            if (body.includes("check your sms")) return 'SMS_REQUIRED';

            // Check input fields for Checkpoint
            var inputs = document.querySelectorAll("input");
            for (var i=0; i<inputs.length; i++) {
                if (inputs[i].offsetParent !== null) {
                    var attr = (inputs[i].name + " " + inputs[i].placeholder + " " + inputs[i].getAttribute("aria-label")).toLowerCase();
                    if (attr.includes("code") || attr.includes("security") || inputs[i].type === "tel" || inputs[i].type === "number") {
                        return 'CHECKPOINT';
                    }
                }
            }
            if (body.includes("check your email")) return 'CHECKPOINT';

            var hasInput = document.querySelector("input[name='code']") || document.querySelector("input[placeholder*='Code']");
            var hasNext = false;
            var btns = document.querySelectorAll("button, div[role='button']");
            for (var b of btns) { if (b.innerText.toLowerCase().includes("next") || b.innerText.toLowerCase().includes("tiếp")) hasNext = true; }

            if (hasInput && body.includes("authentication app") && hasNext) return 'OTP_INPUT_SCREEN';
            return 'UNKNOWN';
        }
        return checkState();
        """
        try: return self.driver.execute_script(js_sensor)
        except: return 'UNKNOWN'

    def _solve_internal_checkpoint(self, gmx_user, gmx_pass, target_ig_username):
        print(f"   [Step 4] Solving Internal Checkpoint for {target_ig_username}...")
        checkpoint_passed = False
        start_time = time.time()
        max_duration = 120  # Timeout tổng 120s để tránh treo
        
        for mail_attempt in range(1, 4):
            if time.time() - start_time > max_duration:
                raise Exception("STOP_FLOW_2FA: Checkpoint timeout after 120s")
            
            print(f"   [Step 4] Mail Retrieval Attempt {mail_attempt}/3...")
            code = get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username)
            
            if not code:
                if self._get_page_state() in ['SELECT_APP', 'ALREADY_ON']: 
                    checkpoint_passed = True; break
                print("   [Step 4] Code not found. Clicking 'Get new code'...")
                self.driver.execute_script("var a=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of a){if(e.innerText.toLowerCase().includes('get a new code')){e.click();break;}}")
                # Poll for new code (giảm xuống 2 lần)
                for poll in range(2):
                    time.sleep(1.5)  # Giảm xuống 1.5s
                    code = get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username)
                    if code: break
                if not code:
                    print("   [Step 4] Still no code after polling. Continuing to next attempt...")
                    continue 

            print(f"   [Step 4] Inputting Code: {code}")
            if self._robust_fill_input(code):
                self._click_continue_robust()
                time.sleep(1)  # Chờ UI update sau click
                is_wrong_code = False
                print("   [Step 4] Verifying...")
                time.sleep(1.5)  # Giảm xuống 1.5s

                verify_attempts = 0
                while verify_attempts < 6:  # Giảm xuống 6
                    if time.time() - start_time > max_duration:
                        raise Exception("STOP_FLOW_2FA: Checkpoint timeout during verification")
                    
                    time.sleep(0.8)  # Giảm xuống 0.8s
                    curr = self._get_page_state()
                    if curr in ['SELECT_APP', 'ALREADY_ON']:
                        checkpoint_passed = True; print("   [Step 4] Checkpoint Passed!"); break
                    
                    err_msg = self.driver.execute_script("return document.body.innerText.toLowerCase()")
                    if ("isn't right" in err_msg or "không đúng" in err_msg or "incorrect" in err_msg or 
                        "the code you entered" in err_msg or "mã bạn đã nhập" in err_msg or "wrong code" in err_msg or 
                        "code is invalid" in err_msg or "mã không hợp lệ" in err_msg):
                        print(f"   [WARNING] Code {code} REJECTED."); is_wrong_code = True; break
                    
                    print("   [Step 4] Not verified yet, retrying confirm...")
                    self._click_continue_robust()
                    verify_attempts += 1

                if checkpoint_passed: break
                if is_wrong_code:
                    print("   [Step 4] Code rejected. Clearing input and requesting new code...")
                    # Clear input trước khi get new code
                    try:
                        input_el = self.driver.find_element(By.CSS_SELECTOR, "input[name='code'], input[placeholder*='Code']")
                        input_el.send_keys(Keys.CONTROL + "a"); input_el.send_keys(Keys.DELETE)
                    except: pass
                    # Click Get new code
                    self.driver.execute_script("var a=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of a){if(e.innerText.toLowerCase().includes('get a new code')){e.click();break;}}")
                    # Chờ mail mới với poll (giảm xuống 2 lần)
                    print("   [Step 4] Waiting for new code in mail...")
                    for poll in range(2):
                        time.sleep(1.5)
                        new_code = get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username)
                        if new_code and new_code != code:  # Đảm bảo code mới khác code cũ
                            print(f"   [Step 4] New code received: {new_code}")
                            code = new_code
                            break
                    else:
                        print("   [Step 4] No new code after polling. Will retry in next attempt.")
                    continue
            else: time.sleep(1)
        
        if checkpoint_passed:
            return True
        else:
            raise Exception("STOP_FLOW_2FA: CHECKPOINT_MAIL: NO CODE")

    def _select_auth_app_method(self, current_state):
        if self._get_page_state() == 'ALREADY_ON': return
        try:
            self.driver.execute_script("""
                var els = document.querySelectorAll("div[role='button'], label");
                for (var i=0; i<els.length; i++) {
                     if (els[i].innerText.toLowerCase().includes("authentication app")) { els[i].click(); break; }
                }
            """)
        except: pass
        self._click_continue_robust()
        poll_end = time.time() + 30
        while time.time() < poll_end:
            state = self._get_page_state()
            if state == 'ALREADY_ON': return
            if len(self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Copy key') or contains(text(), 'Sao chép')]") ) > 0: return
            time.sleep(1)

    def _extract_secret_key(self, ig_username):
        """Lấy Secret Key (Có logic Anti-Freeze: Thoát nếu lỗi trang)."""
        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            secret_key = ""
            end_wait = time.time() + 80  # Chờ tối đa 80 giây
            while time.time() < end_wait:
                try:
                    # [ANTI-FREEZE Check]
                    current_state = self._get_page_state() # Check nhanh bằng JS
                    if current_state == 'BROKEN' or current_state == 'SUSPENDED':
                         raise Exception("STOP_FLOW_2FA: Page Broken/Suspended while waiting for key")
                    if "two_factor" not in self.driver.current_url and "challenge" not in self.driver.current_url:
                         raise Exception("STOP_FLOW_2FA: Redirected away from 2FA page")
                    if current_state == 'ALREADY_ON': return "ALREADY_2FA_ON"

                    # Kiểm tra sự xuất hiện của "Copy key" button trước khi extract
                    copy_key_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
                    has_copy_key = any('Copy key' in btn.text or 'Sao chép' in btn.text for btn in copy_key_buttons)
                    
                    if has_copy_key:
                        # Click "Copy key" button để copy vào clipboard
                        try:
                            copy_button = next(btn for btn in copy_key_buttons if 'Copy key' in btn.text or 'Sao chép' in btn.text)
                            # Clear clipboard trước khi copy
                            pyperclip.copy('')
                            # Scroll to button and use JS click to avoid interception
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", copy_button)
                            time.sleep(0.5)
                            self.driver.execute_script("arguments[0].click();", copy_button)
                            time.sleep(1.0)  # Tăng delay để chờ copy hoàn tất
                            raw_key = pyperclip.paste().replace(" ", "").strip()
                            print(f"   [Step 4] Copied from clipboard: {raw_key}")
                            if len(raw_key) >= 16 and re.match(r'^[A-Z2-7]+$', raw_key):
                                # Skip if it contains the username (case insensitive)
                                if ig_username.lower() in raw_key.lower():
                                    print(f"   [Step 4] Skipped potential key containing username: {raw_key}")
                                    continue
                                secret_key = raw_key
                                break
                            else:
                                print(f"   [Step 4] Invalid key from clipboard: {raw_key}")
                        except Exception as e:
                            print(f"   [Step 4] Error clicking Copy key or getting from clipboard: {e}")
                            # Fallback: Lấy trực tiếp từ span element
                            try:
                                secret_span = self.driver.find_element(By.CSS_SELECTOR, 'span[class*="x1lliihq"]')
                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", secret_span)
                                time.sleep(0.5)
                                raw_key = secret_span.text.replace(" ", "").strip()
                                print(f"   [Step 4] Fallback extracted from span: {raw_key}")
                                if len(raw_key) >= 16 and re.match(r'^[A-Z2-7]+$', raw_key):
                                    if ig_username.lower() in raw_key.lower():
                                        print(f"   [Step 4] Skipped potential key from span: {raw_key}")
                                        continue
                                    secret_key = raw_key
                                    break
                                else:
                                    print(f"   [Step 4] Invalid key from span: {raw_key}")
                            except Exception as e2:
                                print(f"   [Step 4] Fallback span extraction failed: {e2}")
                    else:
                        print("   [Step 4] 'Copy key' button not detected. Waiting...")
                        # Nếu chưa có "Copy key", tiếp tục chờ
                        continue

                    if current_state == 'OTP_INPUT_SCREEN' and not secret_key:
                        print("   [Step 4] Warning: Skiped to OTP screen! Clicking Back...")
                        self.driver.execute_script("var b = document.querySelector('div[role=\"button\"] svg'); if(b) b.closest('div[role=\"button\"]').click();")
                        time.sleep(1); continue

                    # Fallback: regex trên body text (nếu cần)
                    if not secret_key:
                        full_text = self.driver.find_element(By.TAG_NAME, "body").text
                        m = re.search(r'([A-Z2-7]{4}\s?){4,}', full_text)
                        if m:
                            clean = m.group(0).replace(" ", "").strip()
                            if len(clean) >= 16:
                                # Skip if it contains the username (case insensitive)
                                if clean.lower()  in  ig_username.lower():
                                    print(f"   [Step 4] Skipped potential key containing username: {clean}")
                                    continue
                                secret_key = clean; break

                    if not secret_key:
                        inputs = self.driver.find_elements(By.TAG_NAME, "input")
                        for inp in inputs:
                            val = inp.get_attribute("value")
                            if val:
                                clean_val = val.replace(" ", "").strip()
                                if len(clean_val) >= 16 and re.match(r'^[A-Z2-7]+$', clean_val):
                                    # Skip if it contains the username
                                    if ig_username.lower() in clean_val.lower():
                                        print(f"   [Step 4] Skipped potential key from input containing username: {clean_val}")
                                        continue
                                    secret_key = clean_val; break
                    if len(secret_key) >= 16: break
                except Exception as e:
                    if "STOP_FLOW" in str(e): raise e
                    pass
                time.sleep(0.5)  # Giảm từ 1s xuống 0.5s để poll nhanh hơn

            if secret_key: return secret_key
            else:
                print(f"   [Step 4] Secret Key NOT found! Attempt {attempt}/{max_attempts}.")
                time.sleep(2)

        raise Exception("STOP_FLOW_2FA: Secret Key NOT found after 10 retries! Blocking flow.")
    def _validate_masked_email_robust(self, primary_email, secondary_email=None):
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r'\b([a-zA-Z0-9][\w\*]*@[\w\*]+\.[a-zA-Z\.]+)\b', body_text)
            if not match: return True 
            masked = match.group(1).lower().strip()
            print(f"   [Step 4] Mask Hint: {masked}")
            def check(real, mask):
                if not real or "@" not in real: return False
                r_u, r_d = real.lower().split("@"); m_u, m_d = mask.lower().split("@")
                if m_d[0] != '*' and m_d[0] != r_d[0]: return False
                if "." in m_d and m_d.split('.')[-1] != r_d.split('.')[-1]: return False
                if m_u[0] != '*' and m_u[0] != r_u[0]: return False
                return True
            if check(primary_email, masked): return True
            if secondary_email and check(secondary_email, masked): return True
            print(f"   [CRITICAL] Hint {masked} mismatch!"); return False
        except: return True

    def _click_continue_robust(self):
        return self.driver.execute_script("""
            var keywords = ["Next", "Tiếp", "Continue", "Submit", "Xác nhận", "Confirm", "Done", "Xong", "This Was Me", "Đây là tôi", "Đúng là tôi"];
            var btns = document.querySelectorAll("button, div[role='button']");
            for (var b of btns) {
                var txt = b.innerText.trim();
                for(var k of keywords) { 
                    if(txt.includes(k) && b.offsetParent !== null && !b.disabled && b.offsetHeight > 0) { b.click(); return true; } 
                }
            }
            return false;
        """)

    def _robust_fill_input(self, text_value):
        val = str(text_value).strip()
        
        def fill_action():
            input_el = self._find_code_input()
            if not input_el:
                return False
            
            # Nhập từng ký tự với delay để mô phỏng nhập thật
            ActionChains(self.driver).move_to_element(input_el).click().perform()
            # Đảm bảo xóa code cũ: select all và delete
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.DELETE).perform()
            input_el.clear()  # Thêm clear() để đảm bảo
            for char in val:
                input_el.send_keys(char)
                time.sleep(0.05)  # Giảm delay xuống 0.05s để nhập nhanh hơn
            time.sleep(0.3)  # Giảm wait xuống 0.3s
            return input_el.get_attribute("value").replace(" ", "") == val
        
        try:
            return self._safe_element_action(fill_action)
        except Exception as e:
            print(f"   [Step 4] Input fill failed after retries: {e}")
            return False