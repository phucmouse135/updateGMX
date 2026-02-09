# step1_login.py
import json
import time
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from config_utils import wait_element, wait_and_click, wait_and_send_keys, wait_dom_ready

class InstagramLoginStep:
    def __init__(self, driver, username=None, password=None):
        self.driver = driver
        self.username = username
        self.password = password
        self.base_url = "https://accountscenter.instagram.com/"
        self.two_fa_url = "https://accountscenter.instagram.com/password_and_security/two_factor/"
        self.count = 0

    def load_cookies_from_string(self, cookie_str):
        """
        Load cookies from a string (tab-separated or similar format).
        """
        if not cookie_str:
            print("   [Cookie Login] No cookie string provided.")
            return False

        try:
            print("   [Cookie Login] Loading cookies from string...")
            self.driver.get(self.base_url)  # Visit to set domain
            
            # Parse cookies from string, assuming format like name=value; name2=value2;
            cookies = []
            if ';' in cookie_str:
                pairs = cookie_str.split(';')
                for pair in pairs:
                    if '=' in pair:
                        name, value = pair.strip().split('=', 1)
                        cookies.append({'name': name, 'value': value})
            else:
                # If not standard format, try to parse as JSON or other
                try:
                    data = json.loads(cookie_str)
                    cookies = data.get("cookies", [])
                except:
                    print("   [Cookie Login] Cookie string format not recognized.")
                    return False
            
            for cookie in cookies:
                cookie_dict = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': '.instagram.com',
                    'path': '/',
                    'secure': True
                }
                if 'expiry' in cookie:
                    cookie_dict['expiry'] = cookie['expiry']
                try:
                    self.driver.add_cookie(cookie_dict)
                except Exception as e:
                    print(f"   [Cookie Login] Failed to add cookie {cookie.get('name')}: {e}")
            
            self.driver.refresh()
            wait_dom_ready(self.driver, timeout=5)
            return True
        except Exception as e:
            print(f"   [Cookie Login] Error loading cookies from string: {e}")
            return False

    def _wait_for_login_result(self, timeout=120):
        print(f"   [{self.username}] [Status Check] Waiting for login result...")
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            status = self._detect_initial_status()
            print(f"   [{self.username}] [Status Check] Intermediate login status: {status}")
            
            if status == "FAIL_LOGIN_REDIRECTED_TO_PROFILE_SELECTION":
                if self.password:
                    self._handle_profile_selection_login()
                    continue
                else:
                    return status
            
            # Nếu status đã rõ ràng (không phải Unknown/Retry) -> Return ngay
            if status not in ["LOGGED_IN_UNKNOWN_STATE"]:
                return status
            
            time.sleep(1)  # Reduced from 2 to 1 for speed
            
        return "TIMEOUT_LOGIN_CHECK"
    def _detect_initial_status(self):
        """
        Quét DOM để xác định trạng thái sơ bộ sau khi nhấn Login.
        (GIỮ NGUYÊN TEXT LỖI TỪ BẢN GỐC)
        """
        try:
            wait_dom_ready(self.driver, timeout=5)
            
            # Check URL for 2FA page (direct access indicates successful login)
            current_url = self.driver.current_url.lower()
            if "accounts/login" in current_url:
                return "COOKIE_DIE"
            
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            except Exception as e:
                error_str = str(e).lower()
                if "stale" in error_str or "element" in error_str and "reference" in error_str:
                    print(f"   [{self.username}] [Status Check] Stale element when getting body text, retrying...")
                    time.sleep(1)
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except Exception as e2:
                        print(f"   [{self.username}] [Status Check] Stale element retry also failed, returning unknown state")
                        return "LOGGED_IN_UNKNOWN_STATE"
                else:
                    return f"ERROR_DETECT: {str(e)}"
                
            # The login information you entered is incorrect
            if "the login information you entered is incorrect" in body_text or \
                       "incorrect username or password" in body_text or \
                        "thông tin đăng nhập bạn đã nhập không chính xác" in body_text:
                return "LOGIN_FAILED_INCORRECT"
            
            if "choose a way to recover" in body_text:
                return "RECOVERY_CHALLENGE"
            
            # Choose if we process your data for ads
            if "choose if we process your data for ads" in body_text or "chọn nếu chúng tôi xử lý dữ liệu của bạn cho quảng cáo" in body_text:
                return "DATA_PROCESSING_FOR_ADS"
            
            # Check for no internet connection
            if "we couldn't connect to instagram" in body_text and "make sure you're connected to the internet" in body_text:
                return "NOT_CONNECT_INSTAGRAM"
            
            # 1. Các trường hợp Exception / Checkpoint
            if "enter the 6-digit code" in body_text and ("email" in body_text or "mail" in body_text):
                return "CHECKPOINT_MAIL"
            if "check your email" in body_text or " we sent to the email address" in body_text:
                return "CHECKPOINT_MAIL"
            
            # Enter the 6-digit code we sent to the number ending in
            if "enter the 6-digit code we sent to the number ending in" in body_text:
                return "CHECKPOINT_PHONE"
            
            # enter your email
            if "enter your email" in body_text or "please enter your email address to continue" in body_text:
                return "DISABLE_ACCOUNT"
            
            # Log in on another device to continue
            if "log in on another device to continue" in body_text or "đăng nhập trên thiết bị khác để tiếp tục" in body_text:
                return "LOG_IN_ANOTHER_DEVICE"
            
            if "add phone number to get back into instagram" in body_text or "send confirmation" in body_text or "log into another account" in body_text or "we will send a confirmation code via sms to your phone." in body_text: 
                return "SUSPENDED_PHONE"
            # this was me / let us know if it was you
            if "this was me" in body_text or "let us know if it was you" in body_text or "to secure your account" in body_text:
                return "CONFIRM_TRUSTED_DEVICE"
            
            # yêu cầu đổi mật khẩu 
            if "we noticed unusual activity" in body_text or "change your password" in body_text or "yêu cầu đổi mật khẩu" in body_text:
                return "REQUIRE_PASSWORD_CHANGE"
            
            # Nếu đã vào trong (có Post/Follower/Nav bar)
            if "posts" in body_text or "followers" in body_text or "search" in body_text or "home" in body_text:
                return "LOGGED_IN_SUCCESS"

            if("save your login info?" in body_text or "we can save your login info on this browser so you don't need to enter it again." in body_text or "lưu thông tin đăng nhập của bạn" in body_text or "save info" in body_text):
                return "LOGGED_IN_SUCCESS"
            
            
            
            
            
            try:
                wait_dom_ready(self.driver, timeout=5)
                start_time = time.time()
                last_url = self.driver.current_url
                while True:
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except Exception as e:
                        error_str = str(e).lower()
                        if "stale" in error_str or ("element" in error_str and "reference" in error_str):
                            print(f"   [{self.username}] [Status Check] Stale element in status check loop, retrying...")
                            time.sleep(1)
                            continue
                        else:
                            raise e  # Re-raise to be caught by outer except
                    current_url = self.driver.current_url

                    # you need to request help logging in To secure your account, you need to request help logging in
                    if "you need to request help logging in" in body_text or "to secure your account, you need to request help logging in" in body_text:
                        return "GET_HELP_LOG_IN"
                    
                    # We Detected An Unusual Login Attempt 
                    if ("we detected an unusual login attempt" in body_text or "to secure your account, we'll send you a security code." in body_text) :
                        if "email" in body_text or "mail" in body_text:            
                            return "CONTINUE_UNUSUAL_LOGIN"
                        if "this was me" in body_text or "let us know if it was you" in body_text:
                            return "CONFIRM_TRUSTED_DEVICE"
                        return "CONTINUE_UNUSUAL_LOGIN_PHONE"
                
                    if "choose a way to recover" in body_text:
                        return "RECOVERY_CHALLENGE"
                    # 1. Các trường hợp Exception / Checkpoint
                    if "check your email" in body_text or " we sent to the email address" in body_text:
                        return "CHECKPOINT_MAIL"

                    # Log in on another device to continue
                    if "log in on another device to continue" in body_text or "đăng nhập trên thiết bị khác để tiếp tục" in body_text:
                        return "LOG_IN_ANOTHER_DEVICE"
                    
                    # your account has been disabled
                    if "your account has been disabled" in body_text:
                        return "ACCOUNT_DISABLED"

                    if "add phone number to get back into instagram" in body_text or "send confirmation" in body_text or "log into another account" in body_text or "we will send a confirmation code via sms to your phone." in body_text: 
                        return "SUSPENDED_PHONE"

                    # yêu cầu đổi mật khẩu 
                    if "we noticed unusual activity" in body_text or "change your password" in body_text or "yêu cầu đổi mật khẩu" in body_text:
                        return "REQUIRE_PASSWORD_CHANGE"
                    # this was me / let us know if it was you
                    if "this was me" in body_text or "let us know if it was you" in body_text or "to secure your account" in body_text:
                        return "CONFIRM_TRUSTED_DEVICE"

                    # Try another device to continue
                    if "try another device" in body_text or "try another device to continue" in body_text or "can’t try another device?" in body_text:
                        return "TRY_ANOTHER_DEVICE"

                    if "suspended" in body_text or "đình chỉ" in body_text:
                        return "SUSPENDED"

                    # The login information you entered is incorrect
                    if "the login information you entered is incorrect" in body_text or \
                       "incorrect username or password" in body_text or \
                        "thông tin đăng nhập bạn đã nhập không chính xác" in body_text:
                        return "LOGIN_FAILED_INCORRECT"
                    # Something went wrong
                    if "something went wrong" in body_text or "something went wrong" in body_text:
                        return "LOGIN_FAILED_SOMETHING_WENT_WRONG"

                    # 2. Các trường hợp Thành công / Tiếp tục
                    if "select your birthday" in body_text or "add your birthday" in body_text:
                        return "BIRTHDAY_SCREEN"

                    # 
                    # check your text messages
                    if "check your text messages" in body_text or "kiểm tra tin nhắn văn bản của bạn" in body_text:
                        return "2FA_TEXT_MESSAGE"
                    
                    # if "allow the use of cookies" in body_text:
                    #     return "COOKIE_CONSENT"
                    
                    
                    
                    # Help us confirm it's you
                    if "help us confirm it's you" in body_text or "xác nhận đó là bạn" in body_text:
                        return "CONFIRM_YOUR_IDENTITY"

                    

                    # SMS 2FA screen "Enter a 6-digit login code generated by an authentication app." or vietnamese
                    if "mã đăng nhập 6 chữ số được tạo bởi ứng dụng xác thực" in body_text or "enter a 6-digit login code generated by an authentication app." in body_text:
                        return "2FA_SMS"

                    # Check your WhatsApp messages 
                    if "check your whatsapp messages" in body_text or "kiểm tra tin nhắn whatsapp của bạn" in body_text or "we sent via whatsapp to" in body_text:
                        return "2FA_WHATSAPP"


                    # Confirm your info on the app 
                    if "confirm your info on the app" in body_text:
                        return "2FA_APP"

                    # Use another profile => Văng về chọn tài khoản
                    if "use another profile" in body_text or "Log into Instagram" in body_text:
                        return "FAIL_LOGIN_REDIRECTED_TO_PROFILE_SELECTION"

                    

                    # Check your notifications  && Check your notifications there and approve the login to continue.
                    if "check your notifications" in body_text or "xem thông báo của bạn" in body_text or "check your notifications there and approve the login to continue." in body_text:
                        return "2FA_NOTIFICATIONS"
                    
                    # Nếu đã vào trong (có Post/Follower/Nav bar)
                    if "posts" in body_text or "followers" in body_text or "search" in body_text or "home" in body_text or "suggested for you" in body_text or "more accounts" in body_text:
                        return "LOGGED_IN_SUCCESS"

                    if("save your login info?" in body_text or "we can save your login info on this browser so you don't need to enter it again." in body_text or "lưu thông tin đăng nhập của bạn" in body_text):
                        return "LOGGED_IN_SUCCESS"
                    
                    # Log into Instagram , password input 
                    if "log into instagram" in body_text or "password" in body_text or "mobile number, username, or email" in body_text or "log in with facebook" in body_text or "create new account" in body_text:
                        self.count += 1
                        if self.count >=20:
                            return "LOGIN_FAILED"
                    
                    # Nếu vẫn còn ô password -> Login chưa qua (có thể đang loading)
                    if len(self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) > 0:
                        self.count += 1
                        if self.count >=20:
                            return "LOGIN_FAILED_RETRY"

                    # Nếu không xác định được trạng thái, kiểm tra loading hoặc url đứng yên
                    loading_selectors = [
                        "div[role='progressbar']", "div[aria-busy='true']", "._ab8w", ".loading-spinner", "[data-testid='loading-indicator']"
                    ]
                    loading_found = False
                    for sel in loading_selectors:
                        try:
                            if len(self.driver.find_elements(By.CSS_SELECTOR, sel)) > 0:
                                loading_found = True
                                break
                        except:
                            pass

                    # Nếu có loading hoặc url không đổi thì tiếp tục chờ
                    if loading_found or current_url == last_url:
                        if time.time() - start_time > 120:
                            break
                        time.sleep(1)
                        last_url = current_url
                        continue

                    # Nếu không xác định được trạng thái, trả về Unknown State
                    break
                return "LOGGED_IN_UNKNOWN_STATE"
            except Exception as e:
                return f"ERROR_DETECT: {str(e)}" 
        except Exception as e:
            return f"ERROR_DETECT_EXCEPTION: {str(e)}"
        

    def _handle_profile_selection_login(self):
        try:
            print(f"   [{self.username}] [Step 1] Handling profile selection login...")
            # Click "Log into Instagram" or "Continue"
            login_button = wait_element(self.driver, By.XPATH, "//*[contains(text(), 'Log into Instagram')]", timeout=10)
            wait_and_click(self.driver, login_button)
            # Wait for password input
            password_input = wait_element(self.driver, By.CSS_SELECTOR, "input[type='password']", timeout=10)
            wait_and_send_keys(self.driver, password_input, self.password + Keys.RETURN)
            print(f"   [{self.username}] [Step 1] Entered password and submitted.")
        except Exception as e:
            print(f"   [{self.username}] [Step 1] Failed to handle profile selection login: {e}")
            raise

    def _handle_interruptions(self):
        """
        Chiến thuật 'Aggressive Scan' (Tối ưu hóa bằng JS):
        Gộp kiểm tra Popup và kiểm tra Home vào 1 lần gọi JS để tăng tốc độ.
        """
        print("   [Step 3] Starting Aggressive Popup Scan...")
        
        # QUICK CHECK: Only proceed if there are actually popups to handle
        try:
            has_popups = self.driver.execute_script("""
                // Check for visible dialogs/modals
                var dialogs = document.querySelectorAll('div[role="dialog"], div[role="alertdialog"], div[aria-modal="true"]');
                var hasVisibleDialog = Array.from(dialogs).some(d => d.offsetParent !== null && d.offsetWidth > 0 && d.offsetHeight > 0);
                
                // Check for overlays that might block interaction
                var overlays = document.querySelectorAll('div[aria-hidden="false"], div[data-testid*="modal"], div[style*="z-index"]');
                var hasVisibleOverlay = Array.from(overlays).some(o => {
                    var style = window.getComputedStyle(o);
                    return style.display !== 'none' && style.visibility !== 'hidden' && o.offsetParent !== null && o.offsetWidth > 0 && o.offsetHeight > 0;
                });
                
                // Check for specific popup keywords in body text
                var bodyText = (document.body && document.body.innerText.toLowerCase()) || '';
                var hasPopupKeywords = ['get started', 'bắt đầu', 'agree', 'đồng ý', 'next', 'tiếp', 'allow all cookies', 'cho phép tất cả', 'confirm your account', 'xác nhận tài khoản'].some(k => bodyText.includes(k));
                
                return hasVisibleDialog || hasVisibleOverlay || hasPopupKeywords;
            """)
            
            if not has_popups:
                print("   [Step 3] No popups detected. Skipping popup handling.")
                return  # Exit early if no popups found
        
        except Exception as e:
            print(f"   [Step 3] Error in popup detection: {e}")
            # Continue with normal flow if detection fails
        
        # Check for ad subscription popup and reload if found
        
        
        end_time = time.time() + 120  # Quét trong 120 giây 
        popup_handling_attempts = 0
        max_popup_attempts = 20  # Prevent infinite loops
        
        while time.time() < end_time and popup_handling_attempts < max_popup_attempts: 
            try:
                # Try to click on visible dialog to focus before scrolling
                try:
                    dialogs = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'], div[role='alertdialog'], div[aria-modal='true']")
                    for dialog in dialogs:
                        if dialog.is_displayed():
                            # Click on the dialog to focus it
                            self.driver.execute_script("arguments[0].click();", dialog)
                            break
                except: pass
                
                time.sleep(0.5)
                
                # ---------------------------------------------------------
                # 0. INDIVIDUAL POPUP HANDLERS (Riêng lẻ cho từng loại)
                # ---------------------------------------------------------
                if self._handle_age_verification():
                    print("   [Step 3] Handled Age Verification individually")
                    time.sleep(3)
                    continue
                
                if self._handle_accounts_center():
                    print("   [Step 3] Handled Accounts Center individually")
                    time.sleep(1)
                    continue
                
                if self._handle_cookie_consent():
                    print("   [Step 3] Handled Cookie Consent individually")
                    time.sleep(1)
                    continue
                
                if self._handle_confirm_your_account():
                    print("   [Step 3] Handled Confirm Your Account individually")
                    time.sleep(1)
                    continue
                
                try:
                    current_url = self.driver.current_url.lower()
                    if "ad_free_subscription" in current_url:
                        print("   [Step 3] Detected ad_free_subscription URL. Reloading Instagram...")
                        self.driver.get("https://www.instagram.com/")
                        wait_dom_ready(self.driver, timeout=10)
                        time.sleep(3)
                        return  # Exit after reload
                    
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if "want to subscribe or continue using our products free of charge with ads?" in body_text:
                        print("   [Step 3] Detected ad subscription popup text. Reloading Instagram...")
                        self.driver.get("https://www.instagram.com/")
                        wait_dom_ready(self.driver, timeout=10)
                        time.sleep(3)
                        return  # Exit after reload
                    

                    if ("page isn’t working" in body_text or "http error" in body_text or
                        'something went wrong' in body_text or 'đã xảy ra sự cố' in body_text or
                        "this page isn’t working" in body_text or 'the site is temporarily unavailable' in body_text or
                        "reload" in body_text  or "useragent mismatch" in body_text):
                        print("   [Step 3] Error page detected. Reloading Home...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(4); continue
                except Exception as e:
                    print(f"   [Step 3] Error checking for ad subscription: {e}")
                
                # --------------------------------------------------------- 
                # 1. SEQUENTIAL SCAN (POPUP + HOME) BẰNG JS
                # ---------------------------------------------------------
                action_result = self.driver.execute_script("""
                    // 1. KIỂM TRA HOME TRƯỚC (Điều kiện thoát nhanh)
                    // Nếu thấy icon Home và không có dialog nào che -> Báo về Home ngay
                    var homeIcon = document.querySelector("svg[aria-label='Home']") || document.querySelector("svg[aria-label='Trang chủ']");
                    var dialogs = document.querySelectorAll("div[role='dialog']");
                    var hasVisibleDialog = Array.from(dialogs).some(d => d.offsetParent !== null);
                    
                    if (homeIcon && !hasVisibleDialog) {
                        return 'HOME_SCREEN_CLEAR';
                    }

                    // 2. TỪ KHÓA POPUP
                    const keywords = {
                        'get_started': ['get started', 'bắt đầu'],
                        'agree_confirm': ['agree', 'đồng ý', 'update', 'cập nhật', 'confirm', 'xác nhận'],
                        'next_step': ['next', 'tiếp'],
                        'use_data_opt': ['use data across accounts', 'sử dụng dữ liệu trên các tài khoản'],
                        'cookie': ['allow all cookies', 'cho phép tất cả'],
                        'popup': ['not now', 'lúc khác', 'cancel', 'ok', 'hủy'], 
                        'age_check': ['18 or older', '18 tuổi trở lên', 'trên 18 tuổi'],
                        'account_center_check': ['choose an option', 'accounts center', 'use data across accounts', 'keep using your info across these accounts?'] 
                    };
                    const bodyText = (document.body && document.body.innerText.toLowerCase()) || '';

                    // --- ƯU TIÊN: POPUP "ACCOUNTS CENTER" ---
                    if (keywords.account_center_check.some(k => bodyText.includes(k))) {
                        if (bodyText.includes('keep using your info across these accounts?')) {
                            // Select use info across accounts radio button
                            let radios = document.querySelectorAll('input[type="radio"]');
                            for (let radio of radios) {
                                let label = document.querySelector(`label[for="${radio.id}"]`) || radio.closest('div').querySelector('span, div');
                                if (label && label.innerText.toLowerCase().includes('use info across accounts')) {
                                    radio.click();
                                    if (label) label.click();
                                    let container = radio.closest('div[role="button"]');
                                    if (container) container.click();
                                    let visualCircle = radio.previousElementSibling;
                                    if (visualCircle) visualCircle.click();
                                    // Then click next after a short delay
                                    setTimeout(() => {
                                        let buttons = document.querySelectorAll('button, div[role="button"]');
                                        for (let btn of buttons) {
                                            if (btn.offsetParent !== null && !btn.disabled && (btn.innerText.toLowerCase().trim() === 'next' || btn.innerText.toLowerCase().trim() === 'tiếp')) {
                                                btn.click();
                                            }
                                        }
                                    }, 500);
                                    return 'KEEP_INFO_USE_SELECTED';
                                }
                            }
                        } else {
                            let buttons = document.querySelectorAll('button, div[role="button"], span');
                            for (let btn of buttons) {
                                let t = btn.innerText.toLowerCase().trim();
                                if (btn.offsetParent !== null && !btn.disabled && (t === 'next' || t === 'tiếp' || t === 'continue')) {
                                    btn.click();
                                    if (btn.tagName === 'SPAN' && btn.parentElement) btn.parentElement.click();
                                    return 'ACCOUNTS_CENTER_NEXT';
                                }
                            }
                        }
                    }
                    
                    // --- POST VIOLATES COMMUNITY STANDARDS ---
                    if (bodyText.includes('your post goes against our community standards') || 
                        bodyText.includes('bài đăng của bạn vi phạm các tiêu chuẩn cộng đồng của chúng tôi') || 
                        bodyText.includes('how we make decisions')) {
                        let buttons = document.querySelectorAll('button, div[role="button"]');
                        for (let btn of buttons) {
                            if (btn.innerText.toLowerCase().trim() === 'ok') {
                                btn.click();
                                return 'POST_VIOLATES_OK_CLICKED';
                            }
                        }
                    }
                    
                    // --- UNUSUAL ACTIVITY DETECTED ---
                    if (bodyText.includes('we suspect automated behavior on your account') || 
                        bodyText.includes('prevent your account from being temporarily') || 
                        bodyText.includes('verify you are a real person') || 
                        bodyText.includes('suspicious activity')) {
                        let buttons = document.querySelectorAll('button, div[role="button"]');
                        for (let btn of buttons) {
                            if (btn.innerText.toLowerCase().trim() === 'dismiss') {
                                btn.click();
                                return 'UNUSUAL_ACTIVITY_DETECTED';
                            }
                        }
                    }
                    
                    // --- XỬ LÝ CHECKPOINT TUỔI (RADIO BUTTON) ---
                    let radio18 = document.querySelector('input[type="radio"][value="above_18"]');
                    if (radio18) {
                        radio18.click();
                        let container = radio18.closest('div[role="button"]');
                        if (container) container.click();
                        let visualCircle = radio18.previousElementSibling;
                        if (visualCircle) visualCircle.click();

                        // Auto click Agree sau 1s
                        setTimeout(() => {
                            let btns = document.querySelectorAll('button, div[role="button"]');
                            for(let b of btns) {
                                if(b.innerText.toLowerCase().includes('agree') || b.innerText.toLowerCase().includes('đồng ý')) { b.click(); }
                            }
                        }, 500); 
                        return 'AGE_CHECK_CLICKED';
                    }
                    
                    // Fallback tuổi theo text
                    let ageLabels = document.querySelectorAll("span, label");
                    for(let el of ageLabels) {
                        if (el.innerText.includes("18 or older") || el.innerText.includes("18 tuổi trở lên")) {
                             let parentBtn = el.closest('div[role="button"]');
                             if (parentBtn) { parentBtn.click(); return 'AGE_CHECK_CLICKED'; }
                        }
                    }

                    // Scroll before handling options

                    // A. TÌM VÀ CHỌN OPTION (Use Data)
                    const labels = document.querySelectorAll('div, span, label');
                    for (let el of labels) {
                        if (el.offsetParent === null) continue;
                        let txt = el.innerText.toLowerCase().trim();
                        if (keywords.use_data_opt.some(k => txt === k)) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'OPTION_SELECTED';
                        }
                    }

                    // B. TÌM VÀ CLICK NÚT BẤM CHUNG
                    const elements = document.querySelectorAll('button, div[role="button"]');
                    for (let el of elements) {
                        if (el.offsetParent === null) continue; 
                        let txt = el.innerText.toLowerCase().trim();
                        if (!txt) continue;

                        if (keywords.get_started.some(k => txt === k)) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'GET_STARTED_CLICKED';
                        }
                        if (keywords.agree_confirm.some(k => txt.includes(k))) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'AGREE_CLICKED';
                        }
                        if (keywords.next_step.some(k => txt === k)) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'NEXT_CLICKED';
                        }
                        if (keywords.cookie.some(k => txt.includes(k))) {
                            el.click(); return 'COOKIE_CLICKED';
                        }
                        if (keywords.popup.some(k => txt === k)) {
                            el.click(); return 'POPUP_CLICKED';
                        }
                    }
                    return null;
                """)

                if action_result == 'HOME_SCREEN_CLEAR':
                    print("   [Step 3] Home Screen detected. Verifying no remaining popups...")
                    # Double-check that we're actually ready to proceed
                    time.sleep(2)  # Wait a bit more
                    try:
                        # Check again for any remaining dialogs or overlays
                        final_check = self.driver.execute_script("""
                            var dialogs = document.querySelectorAll('div[role='dialog'], div[role='alertdialog'], div[aria-modal='true']');
                            var hasVisibleDialog = Array.from(dialogs).some(d => d.offsetParent !== null && d.getAttribute('aria-hidden') !== 'true');
                            
                            // Check for overlays that might block interaction
                            var overlays = document.querySelectorAll('div[aria-hidden="false"], div[data-testid*="modal"], div[style*="z-index"]');
                            var hasVisibleOverlay = Array.from(overlays).some(o => {
                                var style = window.getComputedStyle(o);
                                return style.display !== 'none' && style.visibility !== 'hidden' && o.offsetParent !== null;
                            });
                            
                            // Check for unusual login popups specifically
                            var bodyText = (document.body && document.body.innerText.toLowerCase()) || '';
                            var unusualLogin = bodyText.includes('we detected an unusual login attempt') ||
                                              bodyText.includes('continue') ||
                                              bodyText.includes('this was me');
                            
                            return !(hasVisibleDialog || hasVisibleOverlay || unusualLogin);
                        """)
                        
                        if final_check:
                            print("   [Step 3] Home Screen Clear confirmed. Done.")
                            break  # [EXIT LOOP] Đã thành công
                        else:
                            print("   [Step 3] Still have popups/overlays/unusual login elements, continuing...")
                            # Try to handle any remaining unusual login popups
                            self._handle_remaining_popups()
                            popup_handling_attempts += 1
                            continue
                    except Exception as e:
                        print(f"   [Step 3] Error in final verification: {e}")
                        popup_handling_attempts += 1
                        continue

                if action_result:
                    print(f"   [Step 3] Action triggered: {action_result}")
                    
                    if action_result == 'AGREE_CLICKED':
                        time.sleep(3); self._check_crash_recovery()
                    elif action_result == 'OPTION_SELECTED':
                        print("   [Step 3] Option selected. Waiting for Next button...")
                        time.sleep(1)
                    elif action_result == 'AGE_CHECK_CLICKED': 
                        print("   [Step 3] Handled Age Verification (18+). Waiting...")
                        time.sleep(3)
                    elif action_result == 'KEEP_INFO_MANAGE_SELECTED':
                        print("   [Step 3] Selected manage accounts and clicked next. Waiting...")
                        time.sleep(2)
                    elif action_result == 'KEEP_INFO_USE_SELECTED':
                        print("   [Step 3] Selected use info across accounts and clicked next. Waiting...")
                        time.sleep(2)
                    elif action_result == 'UNUSUAL_ACTIVITY_DETECTED':
                        print("   [Step 3] Dismissed unusual activity popup. Waiting...")
                        time.sleep(2)
                    else:
                        time.sleep(1.5)
                    continue

                else:
                    # Fallback: If no specific popup detected, find and click buttons in dialogs
                    self._fallback_click_buttons()
                    popup_handling_attempts += 1
                    continue

                # ---------------------------------------------------------
                # 2. CHECK CRASH (Python side fallback)
                # ---------------------------------------------------------
                try:
                    curr_url = self.driver.current_url.lower()
                    if "ig_sso_users" in curr_url or "/api/v1/" in curr_url or "error" in curr_url:
                        print(f"   [Step 3] Crash URL detected. Reloading Home...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(4); continue

                    body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if ("page isn’t working" in body_text or "http error" in body_text or
                        'something went wrong' in body_text or 'đã xảy ra sự cố' in body_text or
                        "this page isn’t working" in body_text or 'the site is temporarily unavailable' in body_text or
                        "reload" in body_text or "HTTP ERROR" in body_text or "HTTP 500" in body_text or
                        "HTTP 502" in body_text or "HTTP 504" in body_text or "useragent mismatch" in body_text):
                        print("   [Step 3] Error page detected. Reloading Home...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(4); continue
                except: pass

                time.sleep(0.5)

            except Exception as e:
                popup_handling_attempts += 1
                time.sleep(1)
        
        if popup_handling_attempts >= max_popup_attempts:
            print(f"   [Step 3] Exceeded max popup handling attempts ({max_popup_attempts}). Proceeding anyway.")
            return  # Exit the method to continue with navigation

    def _check_crash_recovery(self):
        """Hàm phụ trợ check crash nhanh sau khi click Agree."""
        try:
            wait_dom_ready(self.driver, timeout=5)
        except: pass

    def _handle_remaining_popups(self):
        """Handle any remaining unusual login or other popups that Step 2 might have missed."""
        print("   [Step 3] Attempting to handle remaining popups...")
        try:
            # Try to click Continue or This Was Me buttons
            continue_buttons = self.driver.execute_script("""
                var buttons = document.querySelectorAll('button, div[role="button"]');
                var found = [];
                for (var btn of buttons) {
                    var text = btn.textContent.toLowerCase().trim();
                    if (text.includes('continue') || text.includes('tiếp tục') || 
                        text.includes('this was me') || text.includes('đây là tôi')) {
                        found.push(btn);
                    }
                }
                return found.slice(0, 3); // Return up to 3 buttons
            """)
            
            for btn in continue_buttons:
                try:
                    btn.click()
                    print("   [Step 3] Clicked remaining popup button")
                    time.sleep(3)
                    return True
                except:
                    continue
                    
            # Try ESC key as fallback
            self.driver.execute_script("""
                var event = new KeyboardEvent('keydown', {key: 'Escape'});
                document.dispatchEvent(event);
            """)
            print("   [Step 3] Sent ESC key to close popup")
            time.sleep(2)
            
        except Exception as e:
            print(f"   [Step 3] Error handling remaining popups: {e}")
        
        return False

    def _fallback_click_buttons(self):
        """Fallback: Find visible buttons in popups and click the first one."""
        print("   [Step 3] Fallback: Searching for buttons in popups...")
        
        try:
            # Find all visible dialogs
            dialogs = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'], div[role='alertdialog'], div[aria-modal='true']")
            
            for dialog in dialogs:
                if dialog.is_displayed():
                    # Scroll to the dialog first
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", dialog)
                    time.sleep(0.5)
                    # Find buttons inside the dialog
                    buttons = dialog.find_elements(By.CSS_SELECTOR, "button, div[role='button']")
                    
                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            button_text = button.text.strip()
                            print(f"   [Step 3] Clicking fallback button: '{button_text}'")
                            button.click()
                            time.sleep(2)  # Wait after click
                            return True  # Clicked one, return
                    
                    # If no buttons found, try other clickable elements
                    clickable = dialog.find_elements(By.CSS_SELECTOR, "div[role='button'], span[role='button']")
                    
                    for elem in clickable:
                        if elem.is_displayed() and elem.is_enabled():
                            print("   [Step 3] Clicking fallback clickable element")
                            elem.click()
                            time.sleep(2)
                            return True
            
            print("   [Step 3] No clickable buttons found in popups")
            return False
        
        except Exception as e:
            print(f"   [Step 3] Error in fallback click: {e}")
            return False

    def _handle_age_verification(self):
        """Handle age verification popup individually."""
        try:
            time.sleep(0.5)
            radio = self.driver.find_element(By.CSS_SELECTOR, 'input[type="radio"][value="above_18"]')
            radio.click()
            
            # Try to click container
            try:
                container = radio.find_element(By.XPATH, './ancestor::div[@role="button"]')
                if container:
                    container.click()
            except:
                pass
            
            # Try visual circle
            try:
                visual_circle = radio.find_element(By.XPATH, './preceding-sibling::*')
                if visual_circle:
                    visual_circle.click()
            except:
                pass
            
            # Auto click agree after 0.5s
            time.sleep(0.5)
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
            for b in buttons:
                if 'agree' in b.text.lower() or 'đồng ý' in b.text.lower():
                    b.click()
                    return True
            
            return True  # Even if agree not clicked, age was handled
        except:
            return False

    def _handle_accounts_center(self):
        """Handle accounts center popup individually."""
        try:
            time.sleep(0.5)
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            if 'choose an option' in body_text or 'accounts center' in body_text or 'use data across accounts' in body_text:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"], span')
                for b in buttons:
                    if b.text.lower().strip() in ['next', 'tiếp', 'continue']:
                        b.click()
                        return True
            return False
        except:
            return False

    def _handle_cookie_consent(self):
        """Handle cookie consent popup individually."""
        try:
            time.sleep(0.5)
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
            for b in buttons:
                if 'allow all cookies' in b.text.lower() or 'cho phép tất cả' in b.text.lower():
                    b.click()
                    return True
            return False
        except:
            return False

    def _handle_confirm_your_account(self):
        """Handle 'Confirm Your Account' popup individually."""
        try:
            time.sleep(0.5)
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            if 'confirm your account' in body_text or 'xác nhận tài khoản của bạn' in body_text:
                # 1. Click "Get started" / "Bắt đầu"
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                get_started_clicked = False
                for b in buttons:
                    if 'get started' in b.text.lower() or 'bắt đầu' in b.text.lower():
                        b.click()
                        get_started_clicked = True
                        break
                
                if not get_started_clicked:
                    # Try alternative selectors
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, "button._acan._acap._acas").click()
                        get_started_clicked = True
                    except:
                        pass
                
                wait_dom_ready(self.driver, timeout=10)
                time.sleep(2)
                
                # 2. Select radio button "Use data across accounts" / "Sử dụng dữ liệu trên các tài khoản"
                labels = self.driver.find_elements(By.CSS_SELECTOR, 'label')
                for label in labels:
                    if 'use data across accounts' in label.text.lower() or 'sử dụng dữ liệu trên các tài khoản' in label.text.lower():
                        label.click()
                        break
                
                time.sleep(1)
                
                # 3. Click "Next" / "Tiếp theo"
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                for b in buttons:
                    if 'next' in b.text.lower() or 'tiếp theo' in b.text.lower():
                        b.click()
                        return True
                
                return True  # Even if next not clicked, we handled the popup
            return False
        except:
            return False


def login_instagram_via_cookie(driver, cookie_str, username=None, password=None):
    """
    Login to Instagram using cookies from string and go directly to 2FA setup.
    Returns: (bool, status_string)
    """
    login_step = InstagramLoginStep(driver, username, password)

    # Step 1: Load cookies from string
    print(f"   [{username}] [Step 1] Loading cookies and checking login status...")
    if not login_step.load_cookies_from_string(cookie_str):
        return False, "COOKIE_FORMAT_ERROR"

    # Step 2: Navigate to 2FA setup page to verify login
    print(f"   [{username}] [Step 2] Navigating to 2FA setup page...")
    driver.get(login_step.two_fa_url)
    wait_dom_ready(driver, timeout=10)
    time.sleep(3)

    # Step 3: Check if successfully loaded into 2FA page
    current_url = driver.current_url.lower()
    if "two_factor" in current_url and "accounts/login" not in current_url:
        print(f"   [{username}] [Step 3] Successfully loaded 2FA page. Login successful.")
        print(f"   [{username}] [Step 4] Ready for 2FA setup...")
        return True, "SUCCESS"
    else:
        print(f"   [{username}] [Step 3] Failed to load 2FA page. Current URL: {current_url}")
        return False, "LOGIN_FAILED"
