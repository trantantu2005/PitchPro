# Quy trình 2 – Tổng hợp và đối soát doanh thu cuối ngày

Module độc lập, đọc nguồn giao dịch từ `operations.Payment` và không sửa hóa đơn/phiếu thu QT01.

## Cấu trúc

- `models.py`: kỳ đối soát, sao kê, dòng sao kê, ngoại lệ, khoản treo và thông báo nhắc duyệt.
- `services.py`: tổng hợp dòng tiền, đối chiếu mã/số tiền/ngày giao dịch, fingerprint, phát hiện ngoại lệ và tạo snapshot.
- `views.py` / `urls.py`: API mở kỳ, kiểm quỹ, nhập sao kê, xử lý khoản treo, giải trình, duyệt, khóa sổ, thông báo và xuất CSV.
- `management/commands/dispatch_qt02_reminders.py`: tạo thông báo nội bộ cho Quản lý khi báo cáo đã trình quá 10 phút.
- `tests.py`: kiểm thử luồng đối soát, ngoại lệ, dữ liệu muộn, snapshot và phân quyền.

## Quy ước nghiệp vụ

1. Chỉ `Payment.status='success'` được tính vào dòng tiền. QR `pending` hoặc `cancelled` không được tính.
2. Thu tiền dương; hoàn tiền (`kind='refund'`) âm. Tiền cọc (`kind='deposit'`) được theo dõi là dòng tiền nhận trước, không tự kết luận là doanh thu kế toán.
3. Tiền mặt dự kiến = quỹ đầu ca + thu/hoàn tiền mặt ròng − khoản chi ra khỏi két.
4. Chuyển khoản phải có `bank_reference` thực. Không lấy `request_code` nội bộ thay cho mã giao dịch ngân hàng.
5. Đối chiếu sao kê theo mã tham chiếu và số tiền. Thời điểm QT01 và sao kê được lưu để kiểm tra; tài liệu chưa quy định ngưỡng lệch phút nên hệ thống không tự kết luận sai lệch thời gian. Nếu thời điểm trên sao kê thuộc ngày khác kỳ, hệ thống tạo ngoại lệ.
6. Khoản còn phải thu được tính tại ngày chốt theo `business_day`; nếu thu sau ngày chốt thì phải ghi nhận đúng phương án “đã tất toán sau ngày chốt”.
7. Ngoại lệ chỉ được nhân viên giải trình, Quản lý chấp nhận; hệ thống không tự sửa phiếu thu/hóa đơn gốc.
8. Fingerprint bao gồm các phiếu thu liên quan, kể cả thanh toán sau ngày chốt, chi tiết hóa đơn, kiểm quỹ và sao kê. Nếu dữ liệu nguồn đổi sau khi trình, Quản lý không thể duyệt/khóa.
9. Snapshot báo cáo được tạo khi khóa sổ; CSV sau khóa lấy từ snapshot, không tính lại từ dữ liệu mới.
10. Nhắc duyệt sau 10 phút là thông báo nội bộ. Cần chạy command theo lịch; command không gửi SMS/email và không tự chạy nếu chưa được lập lịch.

## Chạy command nhắc duyệt

Trong thư mục `backend`:

```powershell
.\.venv\Scripts\python.exe manage.py dispatch_qt02_reminders
```

Để tự động chạy, tạo tác vụ trong Windows Task Scheduler lặp mỗi 1 phút, chạy đúng Python trong `.venv` với tham số:

```text
manage.py dispatch_qt02_reminders
```

Thư mục làm việc là thư mục `backend`.
