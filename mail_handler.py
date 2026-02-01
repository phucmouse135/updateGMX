# # mail_handler.py
# import imaplib
# import email
# import re
# import time
# from email.header import decode_header

# # Cấu hình IMAP GMX
# IMAP_SERVER = "imap.gmx.net"
# IMAP_PORT = 993

# def _decode_str(header_value):
#     if not header_value: return ""
#     try:
#         decoded_list = decode_header(header_value)
#         text = ""
#         for content, encoding in decoded_list:
#             if isinstance(content, bytes):
#                 text += content.decode(encoding or "utf-8", errors="ignore")
#             else: text += str(content)
#         return text
#     except: return str(header_value)

# def _extract_code_strict(text):
#     """Trích xuất mã 6-8 số dựa trên mẫu thư Instagram thực tế."""
#     if not text: return None
#     # Xóa tag HTML và khoảng trắng thừa
#     clean_text = re.sub(r'<[^>]+>', ' ', text)
#     clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
#     # Các pattern dựa trên hình ảnh image_389e03.png
#     patterns = [
#         r"identity[:\s\W]+(\d{8})", # Ưu tiên mã 8 số như trong ảnh
#         r"confirm your identity[:\s\W]+(\d{6,8})", 
#         r"security code[:\s\W]+(\d{6,8})",
#         r"mã bảo mật[:\s\W]+(\d{6,8})"
#     ]
#     for pat in patterns:
#         m = re.search(pat, clean_text, re.IGNORECASE)
#         if m: return m.group(1)

#     # Fallback cho thẻ font đặc thù của IG
#     m_html = re.search(r'size=["\']6["\'][^>]*>([\d\s]{6,9})</font>', text, re.IGNORECASE)
#     if m_html: return m_html.group(1).replace(" ", "").strip()
#     return None

# def get_code_from_mail(driver, email_user, email_pass):
#     """Lấy mã xác thực từ Top 3 thư chưa đọc mới nhất qua IMAP."""
#     if not email_user or not email_pass: return None
#     if "@" not in email_user: email_user += "@gmx.net"

#     print(f"   [IMAP] Connecting to {email_user}...")
#     mail = None
#     try:
#         mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
#         mail.login(email_user, email_pass)
#     except Exception as e:
#         print(f"   [IMAP] Login Failed: {e}")
#         return None

#     found_code = None
#     try:
#         # Quét 3 lần để đợi mail về
#         for attempt in range(3):
#             print(f"   [IMAP] Scanning for code in newest unread mails (Attempt {attempt+1}/3)...")
#             mail.select("INBOX")
            
#             # Tìm mail CHƯA ĐỌC từ Instagram
#             status, messages = mail.search(None, '(UNSEEN FROM "Instagram")')
            
#             if status == "OK" and messages[0]:
#                 mail_ids = messages[0].split()
#                 # Sắp xếp ID giảm dần (mới nhất lên đầu)
#                 mail_ids.sort(key=lambda x: int(x), reverse=True)
                
#                 # Quét tối đa 3 thư chưa đọc gần nhất để không bỏ lỡ mã
#                 for mid in mail_ids[:3]:
#                     _, msg_data = mail.fetch(mid, "(RFC822)")
#                     full_msg = email.message_from_bytes(msg_data[0][1])
#                     subject = _decode_str(full_msg["Subject"]).lower()
                    
#                     # Chỉ xử lý thư có tiêu đề liên quan đến xác thực
#                     if any(k in subject for k in ["authenticate", "xác thực", "confirm", "code"]):
#                         body_content = ""
#                         if full_msg.is_multipart():
#                             for part in full_msg.walk():
#                                 if part.get_content_type() == "text/html":
#                                     body_content += part.get_payload(decode=True).decode('utf-8', errors='ignore')
#                         else:
#                             body_content = full_msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
#                         code = _extract_code_strict(body_content)
#                         if code:
#                             print(f"   [IMAP] => SUCCESS: Code {code} found in mail ID {mid}")
#                             found_code = code
#                             break
                    
#                     # Nếu thư không phải mã, đánh dấu đã đọc để lần sau bỏ qua nhanh
#                     mail.store(mid, '+FLAGS', '\\Seen')
                
#                 if found_code: break
            
#             if attempt < 2: time.sleep(4) # Chờ mail về ngắn hơn bản cũ
            
#     except Exception as e:
#         print(f"   [IMAP] Error: {e}")
#     finally:
#         try: mail.logout()
#         except: pass
        
#     return found_code

# mail_handler_v2.py
import imaplib
import email
import re
import time
import socket
from email.header import decode_header

# Cấu hình GMX
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
            else:
                text += str(content)
        return text.strip()
    except:
        return str(header_value)

def _fetch_latest_unseen_mail(gmx_user, gmx_pass, subject_keywords, target_username=None, target_email=None, loop_duration=45):
    if not gmx_user or not gmx_pass: return None
    if "@" not in gmx_user: gmx_user += "@gmx.net"

    mail = None
    start_time = time.time()
    code_pattern = re.compile(r'\b(\d{6,8})\b')

    try:
        socket.setdefaulttimeout(30)  # Increased timeout
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        try:
            mail.login(gmx_user, gmx_pass)
        except Exception as e:
            if any(k in str(e).lower() for k in ["authentication failed", "login failed", "credentials"]):
                raise Exception("GMX_DIE")
            raise e

        print(f"   [IMAP] Connected. Scanning for User: {target_username} | Mail: {target_email}... (timeout: {loop_duration}s)")

        while time.time() - start_time < loop_duration:
            try:
                mail.select("INBOX") 
                status, messages = mail.uid('search', None, '(UNSEEN FROM "Instagram")')
                
                if status != "OK" or not messages[0]:
                    time.sleep(2.5); continue

                mail_ids = messages[0].split()
                mail_ids.sort(key=int, reverse=True)

                for mail_id in mail_ids[:3]:
                    # --- LỚP 1: Check Header ---
                    _, msg_header = mail.uid('fetch', mail_id, '(BODY.PEEK[HEADER])')
                    header_content = email.message_from_bytes(msg_header[0][1])
                    
                    subject = _decode_str(header_content.get("Subject", "")).lower()
                    sender = _decode_str(header_content.get("From", "")).lower()
                    to_addr = _decode_str(header_content.get("To", "")).lower() # Lấy địa chỉ người nhận

                    is_relevant = any(k.lower() in subject for k in subject_keywords)
                    if not is_relevant: continue 

                    # MARK SEEN NGAY LẬP TỨC (Chống đọc lại)
                    try: 
                        mail.uid('store', mail_id, '+FLAGS', '\\Seen')
                        print(f"   [IMAP] Marked mail {mail_id} as seen")
                    except Exception as e:
                        print(f"   [IMAP] Failed to mark seen: {e}")

                    # --- LỚP 2: CHECK NGƯỜI NHẬN (QUAN TRỌNG NHẤT) ---
                    # Nếu có truyền vào target_email (linked_mail), bắt buộc phải khớp
                    if target_email:
                        clean_target_mail = target_email.lower().strip()
                        if clean_target_mail not in to_addr:
                            print(f"   [IMAP] Skipped mail {mail_id}. 'To': {to_addr} != Target: {clean_target_mail}")
                            continue
                    
                    # --- LỚP 3: Tải Body ---
                    _, msg_data = mail.uid('fetch', mail_id, "(RFC822)")
                    full_msg = email.message_from_bytes(msg_data[0][1])
                    body = ""
                    if full_msg.is_multipart():
                        for part in full_msg.walk():
                            if part.get_content_type() == "text/plain":
                                body += part.get_payload(decode=True).decode('utf-8', errors='ignore'); break
                    else:
                        body = full_msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    if not body: body = ""
                    
                    # --- LỚP 4: Validate Username (Fallback nếu không có target_email) ---
                    # Chỉ check username nếu không có target_email (vì mail tối giản không có username)
                    if target_username and not target_email:
                        if target_username.lower().replace("@","") not in body.lower():
                            print(f"   [IMAP] Skipped mail (Username mismatch).")
                            continue

                    # --- LỚP 5: Lấy Code ---
                    match = code_pattern.search(body)
                    if match:
                        code = match.group(1)
                        print(f"   [IMAP] FOUND CODE: {code} for {target_username}")
                        return code
                    
            except Exception as loop_e:
                print(f"   [IMAP Loop Warn] {loop_e}"); time.sleep(2)
        
        elapsed = time.time() - start_time
        print(f"   [IMAP] Timeout after {elapsed:.1f}s: No verification code found for {target_username}")
        print("   [IMAP] Possible reasons: Instagram didn't send email, email delayed, or wrong email address")
        return None

    except Exception as e:
        if str(e) == "GMX_DIE": raise e
        print(f"   [IMAP Error] {e}"); return None
    finally:
        if mail:
            try: mail.close(); mail.logout()
            except: pass

# --- UPDATE API: Thêm tham số target_email ---

def get_verify_code_v2(gmx_user, gmx_pass, target_ig_username, target_email=None):
    keywords = ["verify", "xác thực", "confirm", "code", "security", "mã bảo mật", "is your instagram code"]
    return _fetch_latest_unseen_mail(gmx_user, gmx_pass, keywords, target_ig_username, target_email, loop_duration=30)

def get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username, target_email=None):
    keywords = ["authenticate", "two-factor", "security", "bảo mật", "2fa", "login code", "mã đăng nhập"]
    return _fetch_latest_unseen_mail(gmx_user, gmx_pass, keywords, target_ig_username, target_email, loop_duration=30)