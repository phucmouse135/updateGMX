# step1_login.py
import json
import time
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from config_utils import wait_element, wait_and_click, wait_and_send_keys, wait_dom_ready

class InstagramLoginStep:
    def __init__(self, driver):
        self.driver = driver
        self.base_url = "https://www.instagram.com/"
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
        print("   [Step 1] Waiting for login result...")
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            status = self._detect_initial_status()
            print(f"   [Step 1] Intermediate login status: {status}")
            
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
            
            # Check URL for cookie choice
            current_url = self.driver.current_url.lower()
            if "user_cookie_choice" in current_url:
                return "COOKIE_CONSENT_POPUP"
            
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            except Exception as e:
                error_str = str(e).lower()
                if "stale" in error_str or "element" in error_str and "reference" in error_str:
                    print("   [Step 1] Stale element when getting body text, retrying...")
                    time.sleep(1)
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except Exception as e2:
                        print("   [Step 1] Stale element retry also failed, returning unknown state")
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
                            print("   [Step 1] Stale element in status check loop, retrying...")
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
        

def login_instagram_via_cookie(driver, cookie_str):
    """
    Login to Instagram using cookies from string.
    Returns: (bool, status_string)
    """
    login_step = InstagramLoginStep(driver)
    
    # Load cookies from string
    if not login_step.load_cookies_from_string(cookie_str):
        return False, "COOKIE_FORMAT_ERROR"
    
    # Check if already logged in
    driver.get("https://www.instagram.com/")
    wait_dom_ready(driver, timeout=10)
    time.sleep(3) 
    
    # Wait for login result using the robust detection
    status = login_step._wait_for_login_result(timeout=60)
    
    if status == "LOGGED_IN_SUCCESS":
        return True, "SUCCESS"
    else:
        print(f"   [Cookie Login] Login failed with status: {status}")
        return False, status
    