# main.py
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
from config_utils import get_driver
from ig_login import login_instagram_via_cookie
from two_fa_handler import setup_2fa
from colorama import Fore, init

# Init terminal colors
init(autoreset=True)

# Thread lock for file writing safety
file_lock = threading.Lock()

def process_account(line_data):
    """Process 1 account line"""
    line_data = line_data.strip()
    if not line_data: return

    # Split data by tab
    parts = line_data.split('\t')
    
    # Checks lengths of data
    if len(parts) < 5:
        print(Fore.RED + f"[SKIP] Format error: {line_data[:20]}...")
        return

    # print(parts)
    username = parts[0]
    email = parts[3]      # Email index
    email_pass = parts[4] # Email pass index
    
    # Cookie is usually last
    cookie_str = parts[-1]

    print(Fore.CYAN + f"[{username}] Start processing...")
    driver = None
    result_to_save = None
    
    result_to_save = None
    
    # Retry logic: 3 times login
    MAX_RETRIES = 3
    for attempt in range(1, MAX_RETRIES + 1):
        driver = None
        try:
            print(Fore.YELLOW + f"[{username}] Login attempt {attempt}...")
            # 1. Initialize Browser
            driver = get_driver(headless=True) 
            
            # 2. Login Instagram
            if login_instagram_via_cookie(driver, cookie_str):
                
                # 3. Setup 2FA & Get Key
                print(Fore.CYAN + f"[{username}] Getting 2FA...")
                secret_key = setup_2fa(driver, email, email_pass)
                
                # 4. Save result
                result_to_save = secret_key
                print(Fore.GREEN + f"[{username}] SUCCESS! Key: {secret_key}")
                
                # Success -> quit and break
                try: driver.quit()
                except: pass
                driver = None
                break 

        except Exception as e:
            print(Fore.RED + f"[{username}] Error attempt {attempt}: {str(e)}")
            
            # Close browser
            if driver:
                try: driver.quit()
                except: pass
                driver = None
            
            # If last attempt, confirm failure
            if attempt == MAX_RETRIES:
                error_str = str(e).replace("\n", " ").replace("\t", " ")
                result_to_save = f"ERROR: {error_str}"
                print(Fore.RED + f"[{username}] => CONFIRMED FAILURE after 3 tries.")
    
    # Logic for file writing has been moved down...
    try:
        pass 
            
    finally:
        pass # Dummy

    # --- OUTPUT WRITING ---
    # Check if result_to_save is empty (full 3 exceptions)
    if not result_to_save:
            result_to_save = "UNKNOWN_ERROR"

    # Ensure parts list has enough space to assign to index 2
    while len(parts) <= 2:
            parts.append("")
        
    # Gán kết quả vào vị trí tab thứ 2 (Index 2 là cột thứ 3)
    parts[2] = result_to_save
        
    # Ghép lại thành dòng string
    final_line = "\t".join(parts) + "\n"
        
        # Ghi vào file output.txt (Thread Safe)
    with file_lock:
        try:
            with open("output.txt", "a", encoding="utf-8") as f:
                f.write(final_line)
        except: pass

def main():
    print("--- TOOL AUTO 2FA INSTAGRAM ---")
    
    try:
        with open("input.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Error: input.txt not found")
        return

    # NUMBER OF THREADS
    # 2-3 for weak PC, 5-10 for strong PC
    NUM_THREADS = 1 
    
    print(f"Running {len(lines)} accounts with {NUM_THREADS} threads...")
    
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        executor.map(process_account, lines)

    print("--- COMPLETED ---")

if __name__ == "__main__":
    main()