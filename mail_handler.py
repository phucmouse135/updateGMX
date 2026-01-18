# mail_handler.py
import imaplib
import email
import re
import time
from email.header import decode_header

# Cấu hình IMAP GMX
IMAP_SERVER = "imap.gmx.net"
IMAP_PORT = 993

def _decode_str(header_value):
    if not header_value: return ""
    try:
        decoded_list = decode_header(header_value)
        text = ""
        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                text += content.decode(encoding or "utf-8", errors="ignore")
            else: text += str(content)
        return text
    except: return str(header_value)

def _extract_code_strict(text):
    """Trích xuất code 6-8 số từ nội dung mail."""
    if not text: return None
    clean_text = re.sub(r'<[^>]+>', ' ', text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    patterns = [
        r"confirm your identity[:\s\W]+(\d{6,8})", 
        r"code to confirm your identity[:\s\W]+(\d{6,8})",
        r"security code[:\s\W]+(\d{6,8})",
        r"mã bảo mật[:\s\W]+(\d{6,8})"
    ]
    for pat in patterns:
        m = re.search(pat, clean_text, re.IGNORECASE)
        if m: return m.group(1)

    m_html = re.search(r'size=["\']6["\'][^>]*>([\d\s]{6,9})</font>', text, re.IGNORECASE)
    if m_html: return m_html.group(1).replace(" ", "").strip()
    return None

def get_code_from_mail(driver, email_user, email_pass):
    """
    Sử dụng IMAP để lấy mã từ thư CHƯA ĐỌC MỚI NHẤT TUYỆT ĐỐI.
    """
    if not email_user or not email_pass: return None
    if "@" not in email_user: email_user += "@gmx.net"

    print(f"   [IMAP] Connecting to {email_user}...")
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(email_user, email_pass)
    except Exception as e:
        print(f"   [IMAP] Login Failed: {e}")
        return None

    found_code = None
    try:
        # Thử quét 3 lần, mỗi lần cách nhau 5s
        for attempt in range(3):
            print(f"   [IMAP] Scanning strictly for the absolute newest unread mail (Attempt {attempt+1}/3)...")
            mail.select("INBOX")
            
            # Tìm mail CHƯA ĐỌC từ Instagram
            status, messages = mail.search(None, '(UNSEEN FROM "Instagram")')
            
            if status == "OK" and messages[0]:
                mail_ids = messages[0].split()
                # Sắp xếp ID số học giảm dần: ID lớn nhất (mới nhất) lên đầu
                mail_ids.sort(key=lambda x: int(x), reverse=True)
                
                # --- CHỐT CHẶN: CHỈ XỬ LÝ DUY NHẤT THƯ MỚI NHẤT ---
                latest_id = mail_ids[0] 
                print(f"   [IMAP] Inspecting newest ID: {latest_id}")

                # Fetch và đồng thời đánh dấu là Đã đọc (\Seen) để không bị lấy lại lần sau
                _, msg_data = mail.fetch(latest_id, "(RFC822)")
                full_msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode_str(full_msg["Subject"]).lower()
                
                # Kiểm tra tiêu đề xác thực
                if any(k in subject for k in ["authenticate", "xác thực", "confirm", "code"]):
                    body_content = ""
                    if full_msg.is_multipart():
                        for part in full_msg.walk():
                            if part.get_content_type() == "text/html":
                                body_content += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body_content = full_msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    code = _extract_code_strict(body_content)
                    if code:
                        print(f"   [IMAP] => SUCCESS: Newest Code Found: {code}")
                        found_code = code
                        break # Thoát loop check mail vì đã tìm thấy mã mới nhất
                else:
                    print("   [IMAP] Newest unread mail is not an authentication code. Waiting for next...")
            
            if attempt < 2: time.sleep(5) 
            
    except Exception as e:
        print(f"   [IMAP] Error: {e}")
    finally:
        try: mail.logout()
        except: pass
        
    return found_code