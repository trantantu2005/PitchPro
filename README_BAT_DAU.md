> **Phiên bản tinh gọn:** chỉ giữ 01 chức năng AI tại QT02: gợi ý nguyên nhân chênh lệch và đọc chứng từ.
> QT01 hủy sân theo `cancellation_rules.py`, không dùng AI. Xem `backend/HUONG_DAN_QT02.md`.

# PITCHPRO – DJANGO + SQLITE (TÁCH QUY TRÌNH 1 / QUY TRÌNH 2)

## 1. Cấu trúc thư mục backend

```text
PitchPro/
├── CHAY_WINDOWS.bat
├── index.html
├── assets/
│   ├── css/
│   │   ├── app.css
│   │   └── process_2.css
│   └── js/
│       ├── app.js                       # UI hiện có; QT01 giữ nguyên, gọi module QT02
│       └── process_2/
│           └── reconciliation.js       # UI riêng của QT02
└── backend/
    ├── manage.py
    ├── requirements.txt
    ├── config/
    │   ├── settings.py
    │   └── urls.py
    ├── shared/
    │   ├── api.py                       # API decorator, validation, audit, permissions
    │   └── serializers.py               # Serializer dùng chung cho QT01
    ├── operations/
    │   ├── models.py                    # Dữ liệu dùng chung: sân, khách, đặt sân, hóa đơn, Payment...
    │   ├── admin.py
    │   └── management/commands/seed_demo.py
    ├── process_1/
    │   ├── apps.py
    │   ├── urls.py
    │   └── views.py                     # Đặt sân, nhận/trả sân, hóa đơn, kho, thanh toán
    └── process_2/
        ├── apps.py
        ├── models.py                    # Kỳ đối soát, sao kê, dòng sao kê, ngoại lệ, khoản treo
        ├── services.py                  # Tổng hợp, đối chiếu, phát hiện ngoại lệ, fingerprint
        ├── views.py                     # API QT02
        ├── urls.py
        ├── admin.py
        ├── tests.py
        └── management/commands/dispatch_qt02_reminders.py
```

### Nguyên tắc chia module

- `operations`: lớp dữ liệu dùng chung/nguồn giao dịch. QT01 tạo `Payment`; QT02 chỉ đọc `Payment`.
- `process_1`: chỉ chứa API nghiệp vụ Quy trình 1. Không phải sửa code của QT01 để phát triển đối soát.
- `process_2`: chứa toàn bộ model, service, API, test và command nhắc duyệt của Quy trình 2.
- `shared`: tiện ích dùng chung, không chứa logic nghiệp vụ cụ thể.
- Hai quy trình dùng chung SQLite nhưng tách module nghiệp vụ và URL.

Trong `operations.models` còn hai model `Reconciliation` và `ExceptionCase` cũ để tương thích với schema cũ. QT02 mới **không sử dụng** chúng; QT02 sử dụng `process_2.ReconciliationSession` và `process_2.ReconciliationException`.

## 2. Chạy trên Windows

Yêu cầu Python 3.10 trở lên và Internet lần đầu để cài thư viện.

1. Giải nén dự án.
2. Nhấp đúp `CHAY_WINDOWS.bat`.
3. Script tự tạo `.venv`, cài requirements, tạo migrations, migrate, seed dữ liệu và chạy server.
4. Mở `http://127.0.0.1:8000/`.

Nếu muốn chạy thủ công, mở PowerShell tại `backend/`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py makemigrations operations process_2
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

### Tài khoản demo

| Vai trò | Tài khoản | Mật khẩu |
|---|---|---|
| Nhân viên | `nhanvien` | `PitchPro@2026` |
| Quản lý | `quanly` | `PitchPro@2026` |

Tài khoản chỉ dành cho demo cục bộ. Quản lý là superuser để thuận tiện trình diễn.

## 3. Quy trình 1 – module `process_1`

Các endpoint hiện tại được giữ nguyên để frontend QT01 tiếp tục hoạt động:

| Nghiệp vụ | API |
|---|---|
| Đăng nhập/đăng xuất | `/api/session/` |
| Snapshot frontend | `/api/state/` |
| Đặt sân | `/api/bookings/` |
| Nhận/trả sân | `/api/bookings/{id}/check-in/`, `/check-out/` |
| Danh sách hóa đơn | `/api/invoices/` |
| Thêm dịch vụ | `/api/invoices/{id}/items/` |
| Bán lẻ | `/api/invoices/retail/` |
| Thu cọc | `/api/invoices/{id}/deposit/` |
| Tạo QR demo | `/api/invoices/{id}/qr/` |
| Xác nhận thanh toán | `/api/invoices/{id}/pay/` |
| Nhập kho | `/api/stock/restock/` |

Các khoản QR đang chờ (`Payment.status=pending`) không được tính vào dòng tiền. Chỉ `Payment.status=success` được đưa vào sổ QT02.

## 4. Quy trình 2 – đối soát doanh thu cuối ngày

### 4.1. Nguồn dữ liệu và nguyên tắc

- QT02 lấy phiếu thanh toán từ bảng `operations.Payment`, lọc theo `business_day` và `status=success`.
- Tiền mặt và chuyển khoản được tổng hợp riêng.
- `kind=refund` được tính dòng tiền âm; `deposit` và `settlement` là dòng tiền dương.
- QR pending/cancelled không được tính.
- Chuyển khoản so theo mã tham chiếu ngân hàng thực (`bank_reference`) và số tiền, không dùng `request_code` nội bộ thay thế mã ngân hàng. Thiếu mã tham chiếu sẽ tạo ngoại lệ.
- Thời điểm xác nhận QT01 và thời điểm trên sao kê được lưu để kiểm tra; sao kê có thời điểm thuộc ngày khác kỳ sẽ bị gắn ngoại lệ. Tài liệu chưa quy định ngưỡng lệch phút nên hệ thống hiển thị độ lệch thời gian nhưng không tự kết luận theo một ngưỡng tự đặt.
- QT02 không sửa/xóa hóa đơn, phiếu thu hoặc giao dịch nguồn QT01.
- Tiền mặt được tính theo công thức:

  `Quỹ cuối kỳ dự kiến = Quỹ đầu ca + Thu/hoàn tiền mặt ròng - Khoản chi ra khỏi két`

  `Chênh lệch = Tiền thực kiểm - Quỹ cuối kỳ dự kiến`

  Chênh lệch âm là thiếu; dương là thừa.
- Đây là đối soát dòng tiền/phiếu thanh toán. Bản QT01 hiện chưa có mô hình kế toán ghi nhận doanh thu dồn tích; khoản cọc được theo dõi riêng như dòng tiền nhận trước, không tự kết luận là doanh thu kế toán.

### 4.2. Luồng xử lý

1. Nhân viên mở kỳ đối soát cho ngày đã phát sinh.
2. Nhập quỹ đầu ca, tiền nộp/rút két, tiền mặt thực kiểm và biên bản kiểm quỹ.
3. Nhập sao kê ngân hàng mô phỏng, mỗi dòng theo định dạng `MA_GIAO_DICH,SO_TIEN[,DIEN_GIAI]`.
4. Hệ thống so sánh từng mã và số tiền; phát hiện giao dịch thiếu, thừa, trùng hoặc sai số tiền.
5. Rà soát hóa đơn còn phải thu tại mốc chốt và ghi phương án chuyển kỳ sau/đã tất toán sau ngày chốt.
6. Nhân viên giải trình ngoại lệ, ghi chứng từ và phương án.
7. Quản lý chấp nhận hoặc yêu cầu bổ sung từng ngoại lệ.
8. Nhân viên trình báo cáo.
9. Quản lý duyệt; hệ thống kiểm tra fingerprint để phát hiện giao dịch QT01 thay đổi sau khi trình.
10. Quản lý khóa sổ; hệ thống lưu snapshot báo cáo.
11. Sau 10 phút chưa được duyệt, command `dispatch_qt02_reminders` tạo thông báo nội bộ cho Quản lý (cần được lập lịch chạy mỗi phút).

Ngoại lệ được Quản lý chấp nhận nhưng chưa thể khắc phục sẽ vẫn hiển thị rõ trong báo cáo đã khóa; hệ thống không tự điều chỉnh phiếu thu để ép khớp.

### 4.3. API QT02

| Chức năng | Phương thức / API |
|---|---|
| Xem kỳ theo ngày | `GET /api/reconciliation/?date=YYYY-MM-DD` |
| Mở kỳ | `POST /api/reconciliation/` |
| Lưu kiểm quỹ | `POST /api/reconciliation/{day}/cash/` |
| Nhập sao kê | `POST /api/reconciliation/{day}/bank-statement/` |
| Phát hiện ngoại lệ | `POST /api/reconciliation/{day}/detect/` |
| Phân loại hóa đơn treo | `POST /api/reconciliation/{day}/pending/{invoice_id}/` |
| Nhân viên giải trình | `POST /api/reconciliation/{day}/exceptions/{id}/explain/` |
| Quản lý duyệt/từ chối phương án | `POST /api/reconciliation/{day}/exceptions/{id}/decision/` |
| Kiểm tra và trình báo cáo | `POST /api/reconciliation/{day}/submit/` |
| Quản lý duyệt báo cáo | `POST /api/reconciliation/{day}/approve/` |
| Quản lý trả lại | `POST /api/reconciliation/{day}/return/` |
| Quản lý khóa sổ | `POST /api/reconciliation/{day}/lock/` |
| Tải snapshot CSV | `GET /api/reconciliation/{day}/report.csv` |
| Xem thông báo nhắc duyệt | `GET /api/reconciliation/reminders/` |
| Đánh dấu thông báo đã xem | `POST /api/reconciliation/reminders/{id}/read/` |

### 4.4. Nhắc xác nhận quá hạn

Command tạo thông báo nội bộ khi báo cáo đã trình quá 10 phút:

```powershell
.\.venv\Scripts\python.exe manage.py dispatch_qt02_reminders
```

Để chạy tự động, cấu hình Windows Task Scheduler lặp mỗi 1 phút, chạy command trên với thư mục làm việc là `backend`. Bản demo chỉ tạo thông báo trong ứng dụng, chưa gửi email/SMS.

## 5. Kiểm thử

Kịch bản thao tác giao diện từ đầu đến cuối: `docs/QUY_TRINH_2_KICH_BAN_KIEM_THU.md`.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test operations process_2
```

Các test bao gồm:
- QT01 đặt sân → nhận sân → bán dịch vụ → trả sân → thanh toán.
- QR pending không được tính vào dòng tiền cho đến khi xác nhận.
- Thiếu mã tham chiếu ngân hàng và thời điểm sao kê sai ngày được tạo ngoại lệ.
- Báo cáo snapshot chứa chi tiết phiếu thu nguồn, không chỉ tổng số.
- Command tạo thông báo nội bộ khi báo cáo chờ duyệt quá 10 phút.
- QT02 mở kỳ → kiểm quỹ → nhập sao kê → phát hiện ngoại lệ → giải trình → Quản lý duyệt → trình → duyệt → khóa.
- Nhân viên không có quyền duyệt/khóa.
- Giao dịch QT01 thay đổi sau khi trình sẽ chặn phê duyệt.

## 6. GitHub làm nhóm

Nên phân công:
- Thành viên QT01: `backend/process_1/` và các thay đổi có liên quan ở `operations/models.py` (phải trao đổi trước khi sửa schema dùng chung).
- Bạn phụ trách QT02: `backend/process_2/`, `assets/js/process_2/`, `assets/css/process_2.css`.
- Thay đổi `shared/`, `operations/models.py`, `config/settings.py`, `config/urls.py`, `index.html` là vùng tích hợp chung; cần báo thành viên còn lại và review trước khi merge.

Lệnh tạo branch:

```powershell
git switch -c feature/process-2-reconciliation
git add .
git status
git commit -m "feat(qt02): add reconciliation backend and workflow"
git push -u origin feature/process-2-reconciliation
```

Không commit `.venv/`, `backend/db.sqlite3`, `.env`, mật khẩu riêng hoặc API key.

## 7. Giới hạn của bản demo

- Backend dùng SQLite, phù hợp demo nhóm; khi nhiều người thao tác đồng thời cần cân nhắc PostgreSQL và xử lý khóa cạnh tranh.
- Sao kê ngân hàng nhập bằng tay/mô phỏng; chưa kết nối API ngân hàng. Thời điểm giao dịch là tùy chọn khi nhập sao kê; chưa đặt ngưỡng so khớp lệch phút vì tài liệu nghiệp vụ chưa quy định.
- QT01 hiện chưa có nghiệp vụ hoàn tiền hoàn chỉnh. QT02 đã tính quy ước dòng tiền âm cho `Payment.kind=refund` nếu giao dịch hoàn tiền được bổ sung đúng schema/luồng.
- Chưa có upload file chứng từ thật; hiện ghi mã chứng từ và mô tả trong hồ sơ ngoại lệ.
- Chưa phải phần mềm kế toán; báo cáo đối soát không thay thế bút toán kế toán hoặc phê duyệt theo quy chế tài chính của đơn vị.
- Cấu hình `SECRET_KEY`/DEBUG mặc định chỉ dùng local; không triển khai ra Internet.
