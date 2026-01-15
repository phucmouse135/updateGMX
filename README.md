# Hướng dẫn sử dụng Tool Auto 2FA Instagram

Vui lòng thực hiện theo đúng thứ tự các bước dưới đây để tool hoạt động tốt nhất.

## Bước 1: Chuẩn bị môi trường mạng
*   **Bắt buộc**: Bật **VPN** chuyển vùng sang **USA** (Mỹ) trước khi chạy tool.
*   Instagram rất nhạy cảm với IP, việc dùng IP USA sạch sẽ giúp tránh Checkpoint.

## Bước 2: Cài đặt môi trường Python
Mở Terminal (CMD hoặc PowerPoint) tại thư mục tool và chạy các lệnh sau:

### 2.1. Tạo môi trường ảo (Virtual Environment)
```bash
python -m venv .venv
```

### 2.2. Kích hoạt môi trường ảo
*   **Windows (PowerShell):**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```
*   **Windows (CMD):**
    ```cmd
    .\.venv\Scripts\activate.bat
    ```

### 2.3. Cài đặt thư viện cần thiết
```bash
pip install -r requirement.txt
```
*(Nếu file tên là `requirements.txt`, hãy sửa lệnh tương ứng)*

## Bước 3: Chạy Tool
Sau khi cài đặt xong, chạy lệnh sau để mở giao diện điều khiển:

```bash
python gui_app.py
```

## Lưu ý quan trọng
1.  **Format Input**: File input phải đúng định dạng Tab-separated (copy từ Excel/Google Sheet là chuẩn nhất).
2.  **Giờ hệ thống**: Đảm bảo đồng hồ máy tính được đồng bộ chính xác (Sync Time), nếu lệch giờ mã OTP sẽ bị sai.
3.  **Chrome Driver**: Tool sẽ tự động tải Chrome Driver tương ứng. Hãy đảm bảo bạn đã tắt các Chrome đang chạy ngầm nếu gặp lỗi.
