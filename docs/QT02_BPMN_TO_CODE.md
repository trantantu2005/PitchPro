# QT02 – Ánh xạ BPMN To-Be sang mã nguồn Django

| Hoạt động BPMN | Thành phần mã nguồn | Cách thực hiện |
|---|---|---|
| Chốt phạm vi giao dịch trong ngày | `process_2.views.reconciliation` | Mở một `ReconciliationSession` theo `day`; không cho mở ngày tương lai hoặc ngày đã khóa. |
| Tự động tổng hợp giao dịch và doanh thu | `process_2.services.payments_for_day`, `ledger_totals` | Đọc các `Payment` đã xác nhận theo `business_day`; tách tiền mặt/chuyển khoản và loại phiếu. |
| Lập danh sách giao dịch treo | `process_2.services.pending_invoices` | Tính số còn phải thu tại mốc chốt; không tính QR pending là tiền đã nhận. |
| Rà soát và hoàn tất giao dịch treo | `process_2.views.pending_resolution` | Nhân viên ghi chuyển kỳ sau hoặc đã tất toán sau ngày chốt; không sửa phiếu thu QT01. |
| Phân loại doanh thu theo phương thức | `process_2.services.ledger_totals` | Phân loại theo `Payment.method` và `Payment.kind`. Đây là đối soát dòng tiền, không thay báo cáo doanh thu kế toán. |
| Gửi yêu cầu dữ liệu chuyển khoản | `process_2.views.bank_statement_import` | Bản demo nhận sao kê nhập thủ công; chưa kết nối API ngân hàng thật. |
| Đối chiếu giao dịch chuyển khoản | `process_2.services.bank_comparison` | So mã tham chiếu ngân hàng và số tiền; lưu thời điểm QT01/sao kê, gắn ngoại lệ nếu sao kê thuộc ngày khác kỳ. |
| Kiểm đếm tiền mặt thực tế | `process_2.views.cash_count` | Nhân viên nhập quỹ đầu ca, khoản chi ra khỏi két, tiền thực kiểm và căn cứ kiểm đếm. |
| So sánh số liệu theo phương thức | `process_2.services.reconciliation_summary`, `exception_specs` | Tính chênh lệch quỹ và sao kê; tạo ngoại lệ thiếu/thừa/sai mã/sai tiền/sai ngày. |
| Tạo báo cáo đối soát cuối ngày | `process_2.services.report_payload` | Tạo dữ liệu snapshot gồm tổng hợp, phiếu thu nguồn, sao kê, khoản treo và ngoại lệ. |
| Xác nhận báo cáo | `process_2.views.submit_reconciliation`, `recon_action(approve)` | Nhân viên trình; chỉ Quản lý có quyền duyệt. Fingerprint chặn duyệt nếu dữ liệu nguồn đổi. |
| Nhắc xác nhận quá hạn | `dispatch_qt02_reminders` + API `reminders` | Command tạo thông báo nội bộ sau 10 phút; cần lập lịch chạy mỗi phút. |
| Lưu báo cáo và khóa sổ ngày | `process_2.views.recon_action(lock)`, `report` | Chỉ khóa sau duyệt; lưu snapshot và xuất CSV từ snapshot. |
| Call Activity – xử lý chênh lệch | `ReconciliationException` + các API `explain`, `decision`, `resolve` | Nhân viên giải trình; Quản lý chấp nhận/yêu cầu bổ sung; chỉ đánh dấu đã khớp khi chạy lại và chênh lệch thực sự hết. |

## Các kiểm soát quan trọng

- QT02 không cập nhật hoặc xóa `Invoice`/`Payment` gốc của QT01.
- Không lấy `request_code` nội bộ thay cho mã giao dịch ngân hàng thật.
- Không tự xác nhận giao dịch treo, không tự điều chỉnh số tiền để làm khớp.
- Tiền cọc là dòng tiền nhận trước; không tự kết luận là doanh thu kế toán.
- Tài liệu chưa quy định ngưỡng lệch phút giữa thời điểm xác nhận và thời điểm ngân hàng; mã hiện lưu/hiển thị độ lệch để người kiểm tra quyết định, không tự đặt ngưỡng.
- AI được tích hợp ở một bước duy nhất: nhân viên yêu cầu AI đọc chứng từ/gợi ý nguyên nhân chênh lệch (`ai_analyze_exception`); nhân viên xác nhận, Quản lý quyết định. Không dùng AI cho khoản treo hoặc hủy sân.
- API ngân hàng thật và chữ ký số chưa được cấu hình; sao kê trong bản demo được nhập thủ công.
