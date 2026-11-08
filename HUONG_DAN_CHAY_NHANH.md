# PitchPro – Hướng dẫn chạy nhanh

## Chuẩn bị

Mở Terminal PowerShell trong thư mục **PitchPro** (nơi có `requirements.txt`).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd backend
python manage.py migrate
python manage.py check
```

Lần sau, nếu đã tạo môi trường ảo thì chỉ cần kích hoạt `.venv` và chuyển tới `backend`.

## Cấu hình dịch vụ phân tích chứng từ

```powershell
$env:QT02_AI_PROVIDER = "gemini"
$env:GEMINI_API_KEY = Read-Host "Nhap Gemini API Key"
$env:GEMINI_MODEL = "gemini-3.1-flash-lite"
python manage.py check_qt02_gemini --smoke
python manage.py runserver
```

Nhập API key trong Terminal, không đưa khóa vào mã nguồn. Truy cập <http://127.0.0.1:8000/>.

## Đối soát doanh thu

Đăng nhập bằng tài khoản thuộc nhóm **Staff**, mở **Đối soát cuối ngày**, chọn ngày nghiệp vụ. Sau khi nhập quỹ tiền mặt và sao kê, bấm **Kiểm tra và phát hiện ngoại lệ**. Chức năng phân tích chứng từ xuất hiện khi có hồ sơ ngoại lệ đang mở. Tài khoản **Manager** duyệt giải trình và khóa sổ.

Trong form nhập sao kê, **Tiền mặt đã ghi nhận** và **Chuyển khoản đã ghi nhận** là các số liệu thu ròng từ hệ thống (đã tính tiền hoàn); **Tổng trên sao kê** là số tiền trên các giao dịch ngân hàng do người dùng nhập. Hai nhóm số liệu được đối chiếu, không tự ghi đè lên nhau.

Nút **Điền sao kê mẫu** chỉ phục vụ kiểm thử, không thay thế sao kê ngân hàng thật.

## Dữ liệu và sao lưu

Bản ZIP này có sẵn `backend/db.sqlite3` từ dữ liệu dự án được cung cấp. Nếu đã có dữ liệu mới, **hãy sao lưu file `db.sqlite3` của bản đang chạy trước khi giải nén**. Đừng xóa cơ sở dữ liệu, chạy `flush` hay `seed_demo` vào database đã có giao dịch khi chưa cần thiết.

Nếu giao diện còn giữ bản cũ, nhấn `Ctrl + F5`. Không chia sẻ API key, file `.env` hoặc dữ liệu chứng từ riêng tư.
