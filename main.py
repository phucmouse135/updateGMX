# main.py
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
from config_utils import get_driver
from ig_login import login_instagram_via_cookie
from two_fa_handler import setup_2fa
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
            if login_instagram_via_cookie(driver, cookie_str):
                
                # 3. Setup 2FA & Get Key
                # Truyền đúng email user/pass của GMX vào đây
                print(Fore.CYAN + f"[{username}] Getting 2FA...")
                
                secret_key = setup_2fa(driver, email_user, email_pass, target_username=username)
                
                # 4. Success
                result_to_save = secret_key
                print(Fore.GREEN + f"[{username}] SUCCESS! Key: {secret_key}")
                
                if driver: 
                    try: driver.quit()
                    except: pass
                driver = None
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
    if not result_to_save:
            result_to_save = "UNKNOWN_ERROR"

    # Ghi kết quả vào cột IG2FA (Index 5) theo yêu cầu hoặc ghi vào cột riêng?
    # Thường tool sẽ update lại vào file. 
    # Input mẫu: UID[0] ... IG2FA[5] ...
    # Ta sẽ ghi đè kết quả vào cột IG2FA (parts[5])
    
    # Ensure list size
    while len(parts) <= 5: parts.append("")
    
    parts[5] = result_to_save # Save Key to IG2FA column
    
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