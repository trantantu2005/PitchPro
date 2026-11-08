# Nhật ký tinh gọn dự án PitchPro

## Giữ lại

- QT01: đặt sân, nhận/trả sân, hủy sân theo quy tắc, hóa đơn, thanh toán, quản lý hàng hóa và kho.
- QT02: đối soát tiền mặt/chuyển khoản, sao kê, ngoại lệ, khoản treo xử lý thủ công, duyệt, khóa sổ, lịch sử, chứng từ.
- **Duy nhất một AI:** gợi ý nguyên nhân chênh lệch (ngoại lệ QT02), có thể đọc PDF có lớp văn bản/TXT/CSV và nội dung nhân viên dán.
- Giữ `db.sqlite3`, migrations, models AI lịch sử (để không làm hỏng dữ liệu/migration đang dùng).

## Đã gỡ

- API AI QT01: `/api/invoices/{id}/ai/cancellation/`, `/api/invoices/{id}/ai/discrepancy/`.
- API AI khoản treo QT02: `/api/reconciliation/{day}/ai/pending/`.
- Nút, form, hàm JS gọi 3 chức năng AI trên.
- File `process_1/ai_service.py`, `process_1/ai_views.py`; các file `.bak*`, script sửa chữa chạy một lần; hai `.venv_lab` cũ và cache Python; file backup SQLite `db_backup_before_check.sqlite3`.
- Không xóa `cancellation_rules.py`: đây là quy tắc hủy sân bắt buộc, **không phải AI**.

## Chạy và thử

1. Mở thư mục `backend`; `pip install -r requirements.txt`; `python manage.py migrate`.
2. `python manage.py check`; `python manage.py test operations process_2 -v 2`; `python manage.py runserver`.
3. Đăng nhập demo, thử hủy sân; phần này không được hiện nút AI.
4. Mở QT02, tạo ngoại lệ, gọi AI gợi ý nguyên nhân; kiểm tra nhân viên vẫn là người xác nhận giải trình.

**Lưu ý:** API AI cần cấu hình provider hợp lệ mới chạy thực tế; các test dùng mock nên không tạo chi phí API. CSDL demo có sẵn giữ nguyên dữ liệu gốc.
