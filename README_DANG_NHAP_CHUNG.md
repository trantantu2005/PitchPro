# PITCHPRO – CỔNG ĐĂNG NHẬP CHUNG VÀ PHÂN QUYỀN

## 1. Đường dẫn mới

| URL | Truy cập | Chức năng |
| --- | --- | --- |
| `/` hoặc `/dang-nhap/` | Mọi người chưa đăng nhập | Màn hình đăng nhập chung |
| `/dang-ky/` | Mọi người chưa đăng nhập | Cùng màn hình, mở form đăng ký **Customer** |
| `/khach/` | Customer | Đặt sân, xem sân trống và lịch của tôi |
| `/nhan-vien/` | Staff | Dashboard nghiệp vụ, đặt/nhận/trả sân, kho và đối soát theo quyền |
| `/quan-ly/` | Manager | Dashboard nghiệp vụ, duyệt ngoại lệ, phê duyệt và khóa sổ |

- Mở `/` khi đã đăng nhập → máy chủ tự chuyển sang đúng trang.
- Cố mở trang không đúng vai trò → máy chủ chuyển về khu vực được phép, không render nội dung trang kia.
- Cả `/nhan-vien/` và `/quan-ly/` cùng dùng `index.html` để **không nhân đôi code**. Phân quyền thao tác tiếp tục được backend kiểm tra theo Group.
- Đăng ký mới chỉ cấp nhóm Customer; nhóm Staff/Manager do quản trị viên cấp.
- Đăng xuất từ khu vực nào cũng trở về một màn hình đăng nhập chung.

## 2. Những file đã sửa

**Tạo mới:** `auth.html`, `assets/css/auth.css`, `assets/js/auth.js`, `backend/operations/test_auth_gateway.py`.

**Chỉnh sửa:** `backend/config/urls.py`, `index.html`, `customer.html`, `assets/js/app.js`, `assets/js/customer.js`, `backend/process_1/test_customer.py`.

**Không sửa CSDL:** Không cần makemigrations vì thay đổi này chỉ liên quan giao diện và điều hướng/quyền truy cập.

## 3. Cách cập nhật dự án hiện có

1. **Sao lưu `backend/db.sqlite3`** (và `.env` nếu có). **Không ghi đè DB hiện có.**
2. Dùng gói `ChiFileThayDoi.zip`, giải nén đúng vào gốc dự án (cùng cấp `index.html`, `backend`, `assets`).
3. Trong PowerShell tại gốc dự án:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
cd backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test operations process_1.test_customer process_2
.\.venv\Scripts\python.exe manage.py runserver
```

Nếu môi trường `.venv` chưa tồn tại:

```powershell
py -m venv backend/.venv
```

4. Mở **http://127.0.0.1:8000/**, nhấn `Ctrl+Shift+R` để tải CSS/JS mới.

## 4. Kiểm thử thủ công

1. Đăng nhập `khachhang` → `/khach/`; không xem được `/quan-ly/` hay `/api/state/`.
2. Đăng xuất → `/`.
3. Đăng nhập `nhanvien` → `/nhan-vien/`.
4. Đăng xuất → `/`.
5. Đăng nhập `quanly` → `/quan-ly/`.
6. Đăng xuất, chọn **Đăng ký khách hàng**, tạo tài khoản mới → `/khach/`.
7. Không thử nghiệm với mật khẩu thật trên dữ liệu trình diễn.

## 5. Giới hạn

- Đây là nguyên mẫu học phần. Chưa triển khai khôi phục mật khẩu/OTP hoặc email xác minh.
- Thanh toán cọc trực tuyến chưa được triển khai trong Giai đoạn 2.
- Giao diện dùng HTTPS và khóa bí mật an toàn khi triển khai công khai; không chạy DEBUG tại môi trường thật.
- Kiểm thử Django cần chạy trên máy đã cài thư viện của dự án.
