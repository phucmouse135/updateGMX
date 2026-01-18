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
    """Trích xuất mã 6-8 số dựa trên mẫu thư Instagram thực tế."""
    if not text: return None
    # Xóa tag HTML và khoảng trắng thừa
    clean_text = re.sub(r'<[^>]+>', ' ', text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # Các pattern dựa trên hình ảnh image_389e03.png
    patterns = [
        r"identity[:\s\W]+(\d{8})", # Ưu tiên mã 8 số như trong ảnh
        r"confirm your identity[:\s\W]+(\d{6,8})", 
        r"security code[:\s\W]+(\d{6,8})",
        r"mã bảo mật[:\s\W]+(\d{6,8})"
    ]
    for pat in patterns:
        m = re.search(pat, clean_text, re.IGNORECASE)
        if m: return m.group(1)

    # Fallback cho thẻ font đặc thù của IG
    m_html = re.search(r'size=["\']6["\'][^>]*>([\d\s]{6,9})</font>', text, re.IGNORECASE)
    if m_html: return m_html.group(1).replace(" ", "").strip()
    return None

def get_code_from_mail(driver, email_user, email_pass):
    """Lấy mã xác thực từ Top 3 thư chưa đọc mới nhất qua IMAP."""
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
        # Quét 3 lần để đợi mail về
        for attempt in range(3):
            print(f"   [IMAP] Scanning for code in newest unread mails (Attempt {attempt+1}/3)...")
            mail.select("INBOX")
            
            # Tìm mail CHƯA ĐỌC từ Instagram
            status, messages = mail.search(None, '(UNSEEN FROM "Instagram")')
            
            if status == "OK" and messages[0]:
                mail_ids = messages[0].split()
                # Sắp xếp ID giảm dần (mới nhất lên đầu)
                mail_ids.sort(key=lambda x: int(x), reverse=True)
                
                # Quét tối đa 3 thư chưa đọc gần nhất để không bỏ lỡ mã
                for mid in mail_ids[:3]:
                    _, msg_data = mail.fetch(mid, "(RFC822)")
                    full_msg = email.message_from_bytes(msg_data[0][1])
                    subject = _decode_str(full_msg["Subject"]).lower()
                    
                    # Chỉ xử lý thư có tiêu đề liên quan đến xác thực
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
                            print(f"   [IMAP] => SUCCESS: Code {code} found in mail ID {mid}")
                            found_code = code
                            break
                    
                    # Nếu thư không phải mã, đánh dấu đã đọc để lần sau bỏ qua nhanh
                    mail.store(mid, '+FLAGS', '\\Seen')
                
                if found_code: break
            
            if attempt < 2: time.sleep(4) # Chờ mail về ngắn hơn bản cũ
            
    except Exception as e:
        print(f"   [IMAP] Error: {e}")
    finally:
        try: mail.logout()
        except: pass
        
    return found_code