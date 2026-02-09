# main.py
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
from config_utils import get_driver
from ig_login import login_instagram_via_cookie
from two_fa_handler import Instagram2FAStep
from colorama import Fore, init

init(autoreset=True)
file_lock = threading.Lock()

def process_account(line_data):
    """Process 1 account line with NEW FORMAT"""
    line_data = line_data.strip()
    if not line_data: return

    parts = line_data.split('\t')
    
    # Format mới có khoảng 13 cột. Check tối thiểu 8 cột để lấy Pass Mail
    if len(parts) < 8:
        print(Fore.RED + f"[SKIP] Format error (not enough columns): {line_data[:20]}...")
        return

    # --- MAPPING INPUT MỚI ---
    # 0:UID, 1:addMAIL, 2:LK, 3:IGUSER, 4:PASS, 5:IG2FA, 6:PHÔI_GỐC, 7:PASS_MAIL, ... 12:COOKIE
    
    username = parts[3]    # IG User
    email_user = parts[6]  # PHÔI GỐC (GMX User)
    email_pass = parts[7]  # PASS MAIL (GMX Pass)
    
    # Cookie nằm ở cột 12 (cuối cùng)
    # Cần xử lý trường hợp dòng input bị thiếu cột cuối
    cookie_str = ""
    if len(parts) > 12:
        cookie_str = parts[12]
    else:
        # Fallback: Thử tìm cột nào trông giống cookie (bắt đầu bằng datr= hoặc ds_user_id=)
        for p in parts:
            if "datr=" in p or "ds_user_id=" in p:
                cookie_str = p
                break

    print(Fore.CYAN + f"[{username}] Start processing... (Mail: {email_user})")
    
    driver = None
    result_to_save = None
    
    MAX_RETRIES = 3 # Giữ nguyên logic retry
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(Fore.YELLOW + f"[{username}] Login attempt {attempt}...")
            
            # 1. Initialize Browser (Config tối ưu đã có ở câu trả lời trước)
            driver = get_driver(headless=True) 
            
            # 2. Login Instagram
            login_success, login_status = login_instagram_via_cookie(driver, cookie_str, username=username)
            if login_success:
                
                # 3. Setup 2FA & Get Key (Step 4)
                print(Fore.CYAN + f"[{username}] Step 4: Setting up 2FA...")
                
                instagram_2fa = Instagram2FAStep(driver)
                secret_key = instagram_2fa.setup_2fa(email_user, email_pass, target_username=username)
                
                if secret_key.startswith("FAIL:"):
                    # Update NOTE column for all FAIL errors
                    while len(parts) <= 12: parts.append("")
                    parts[12] = secret_key.replace("FAIL: ", "")  # Remove prefix for cleaner note
                    result_to_save = None  # Explicitly set None to avoid writing to IG2FA
                    print(Fore.YELLOW + f"[{username}] 2FA setup failed: {secret_key}. Updated NOTE.")
                else:
                    # 4. Success
                    result_to_save = secret_key
                    print(Fore.GREEN + f"[{username}] SUCCESS! Key: {secret_key}")
                
                if driver: 
                    try: driver.quit()
                    except: pass
                driver = None
                break 
            
            else:
                # Handle login failure
                if login_status == "ALREADY_ON":
                    # Update NOTE column (assume index 12)
                    while len(parts) <= 12: parts.append("")
                    parts[12] = "ALREADY_ON"
                    result_to_save = None  # Explicitly set None
                    print(Fore.YELLOW + f"[{username}] 2FA already enabled. Updated NOTE.")
                    
                    if driver: 
                        try: driver.quit()
                        except: pass
                    driver = None
                    break # Stop retrying for ALREADY_ON
                else:
                    result_to_save = f"LOGIN_FAIL: {login_status}"
                    print(Fore.RED + f"[{username}] Login failed: {login_status}")
                
                    if driver: 
                        try: driver.quit()
                        except: pass
                    driver = None
                    
                    # Retry logic: Only break if max retries reached
                    if attempt < MAX_RETRIES:
                        print(Fore.YELLOW + f"[{username}] Retrying... ({attempt}/{MAX_RETRIES})")
                        continue
                    else:
                        break 

        except Exception as e:
            print(Fore.RED + f"[{username}] Error attempt {attempt}: {str(e)}")
            if driver:
                try: driver.quit()
                except: pass
                driver = None
            
            if attempt == MAX_RETRIES:
                error_str = str(e).replace("\n", " ").replace("\t", " ")
                result_to_save = f"ERROR: {error_str}"
                print(Fore.RED + f"[{username}] => CONFIRMED FAILURE.")
    
    # --- OUTPUT WRITING ---
    # Logic: Only write to parts[5] if we have a valid result (Success Key or specific Login Fail that isn't handled elsewhere)
    # If result_to_save is None (e.g. handled as NOTE), do not overwrite parts[5].
    
    if result_to_save:
        parts[5] = result_to_save
    
    # Ensure parts[12] (NOTE) exists if we accessed it earlier
    while len(parts) <= 12: parts.append("")
    
    final_line = "\t".join(parts) + "\n"
    
    with file_lock:
        try:
            with open("output.txt", "a", encoding="utf-8") as f:
                f.write(final_line)
        except: pass

def main():
    print("--- TOOL AUTO 2FA INSTAGRAM (GMX IMAP) ---")
    try:
        with open("input.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Error: input.txt not found")
        return

    NUM_THREADS = 2 # Tăng lên vì IMAP nhẹ hơn
    print(f"Running {len(lines)} accounts with {NUM_THREADS} threads...")
    
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        executor.map(process_account, lines)
    print("--- COMPLETED ---")

if __name__ == "__main__":
    main()