import imaplib
import email as py_email
import re
import time

# CẤU HÌNH GMX
IMAP_HOST = "imap.gmx.net"
IMAP_PORT = 993

def extract_instagram_code(text):
    if not text: return None
    
    # 1. ƯU TIÊN: Tìm theo ngữ cảnh "confirm your identity"
    # Mẫu: "confirm your identity: 68345892" (Có thể có xuống dòng hoặc khoảng trắng)
    # \d{6,8} nghĩa là lấy từ 6 đến 8 chữ số
    match_context = re.search(r'identity[:\s\W]*(\d{6,8})', text, re.IGNORECASE)
    if match_context:
        return match_context.group(1)

    # 2. FALLBACK: Tìm mã 6-8 số đứng riêng lẻ (Nếu regex trên trượt)
    # (?<!\d) và (?!\d) để đảm bảo không cắt số từ chuỗi dài hơn
    match_raw = re.search(r'(?<!\d)(\d{6,8})(?!\d)', text)
    if match_raw:
        return match_raw.group(1)
        
    return None

def get_code_from_mail(email_user, password, timeout=40):
    """
    Chỉ lấy mail có tiêu đề 'Authenticate your account'
    """
    print(f"   [GMX-IMAP] Kết nối {email_user}...")
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_user, password)
        mail.select("INBOX")
        
        end_time = time.time() + timeout
        while time.time() < end_time:
            # Lấy 10 mail mới nhất (bất kể đã đọc hay chưa để tránh sót)
            status, data = mail.search(None, 'ALL')
            mail_ids = data[0].split()[-10:] if data and data[0] else []

            for num in reversed(mail_ids):
                try:
                    _, msg_data = mail.fetch(num, '(RFC822)')
                    if not msg_data or not msg_data[0]: continue
                    
                    raw_email = msg_data[0][1]
                    msg = py_email.message_from_bytes(raw_email)
                    
                    subject = str(msg["Subject"]).lower()
                    sender = str(msg["From"]).lower()
                    
                    # --- BỘ LỌC QUAN TRỌNG ---
                    # 1. Người gửi phải là Instagram
                    # 2. Tiêu đề phải chứa "authenticate" hoặc "confirm"
                    is_insta = "instagram" in sender
                    is_target_subject = "authenticate" in subject or "confirm" in subject
                    
                    if is_insta and is_target_subject:
                        # Lấy Body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() in ["text/plain", "text/html"]:
                                    try: body += part.get_payload(decode=True).decode()
                                    except: pass
                        else:
                            try: body = msg.get_payload(decode=True).decode()
                            except: pass
                        
                        # Trích xuất code
                        code = extract_instagram_code(body)
                        if code:
                            print(f"   [GMX-IMAP] -> FOUND CODE: {code} (Subject: {subject})")
                            return code
                except Exception: continue
            
            time.sleep(3)
            
    except Exception as e:
        print(f"   [GMX-IMAP] Lỗi: {e}")
    finally:
        try: 
            if mail: mail.logout()
        except: pass
    
    print("   [GMX-IMAP] Timeout: Không tìm thấy code 'Authenticate'.")
    return None