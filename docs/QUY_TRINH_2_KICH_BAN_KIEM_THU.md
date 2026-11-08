# Kịch bản kiểm thử Quy trình 2 – Đối soát doanh thu

## Chuẩn bị
1. Chạy `CHAY_WINDOWS.bat`.
2. Đăng nhập `nhanvien / PitchPro@2026`.
3. Vào Quy trình 1, tạo một lượt đặt sân trong ngày, nhận sân, trả sân và thanh toán.
4. Tạo ít nhất một khoản chuyển khoản được xác nhận thủ công để có mã tham chiếu ngân hàng.
5. Nếu muốn kiểm tra khoản treo, trả sân nhưng chưa thanh toán một hóa đơn.

## Luồng khớp hoàn toàn
1. Vào **Đối soát cuối ngày**, chọn ngày có giao dịch.
2. Nhấn **Mở kỳ đối soát**.
3. Nhập quỹ đầu ca, khoản chi ra khỏi két và tiền mặt thực kiểm. Công thức: đầu ca + thu/hoàn tiền mặt ròng - chi ra khỏi két.
4. Nhập sao kê. Mỗi dòng: `MÃ_GIAO_DỊCH,SỐ_TIỀN[,DIỄN_GIẢI]`.
   - Lấy mã tham chiếu từ chi tiết hóa đơn / phiếu thanh toán.
   - Nếu ngày đó không có giao dịch ngân hàng, nhập sao kê rỗng.
- Không dùng mã yêu cầu QR nội bộ làm mã tham chiếu ngân hàng; phiếu chuyển khoản thiếu `bank_reference` phải được xử lý ngoại lệ.
5. Phân loại mọi hóa đơn còn phải thu tại thời điểm chốt.
6. Nhấn **Kiểm tra và phát hiện ngoại lệ**.
7. Nếu không còn ngoại lệ mở, nhân viên nhấn **Nhân viên trình báo cáo**.
8. Đăng xuất, đăng nhập `quanly / PitchPro@2026`.
9. Quản lý nhấn **Quản lý duyệt báo cáo**, sau đó **Khóa sổ và lưu snapshot**.
10. Tải báo cáo CSV sau khi khóa.

## Luồng thiếu tiền mặt
1. Làm các bước mở kỳ và nhập sao kê.
2. Nhập tiền thực kiểm thấp hơn quỹ dự kiến 10.000 VNĐ.
3. Nhấn **Kiểm tra và phát hiện ngoại lệ**.
4. Đăng nhập nhân viên, điền nguyên nhân, bằng chứng và phương án xử lý cho ngoại lệ thiếu tiền.
5. Đăng nhập quản lý, chấp nhận hoặc yêu cầu bổ sung phương án.
6. Nếu Quản lý chấp nhận, nhân viên có thể trình báo cáo; báo cáo sẽ lưu nguyên trạng số thiếu và hồ sơ được chấp nhận, không tự cộng tiền để làm khớp.

## Luồng sai mã giao dịch ngân hàng
1. Nhập sao kê với số tiền đúng nhưng thay mã tham chiếu bằng mã không tồn tại.
2. Nhấn **Kiểm tra và phát hiện ngoại lệ**.
3. Hệ thống phải tạo ít nhất hai ngoại lệ: giao dịch có trong sổ nhưng thiếu trên sao kê; giao dịch thừa trên sao kê.
4. Nhân viên giải trình từng ngoại lệ.
5. Quản lý duyệt từng phương án.
6. Khi trình báo cáo, hai ngoại lệ đã được chấp nhận sẽ còn hiển thị trong snapshot; không được xóa giao dịch gốc.

## Kiểm tra phân quyền và tính toàn vẹn
- Nhân viên gọi API duyệt hoặc khóa phải nhận HTTP 403.
- Quản lý không thể duyệt nếu kỳ chưa được nhân viên trình.
- Nếu QT01 phát sinh thêm Payment hoặc thay đổi hóa đơn sau khi trình, fingerprint thay đổi và API chặn duyệt/khóa.
- Quản lý phải trả kỳ về nháp; ngoại lệ được duyệt trước đó phải rà soát lại.
- Sau khi khóa, QT01 không được ghi thêm giao dịch vào ngày đã khóa.
- CSV tải sau khi khóa phải lấy từ `report_snapshot`, không tính lại từ giao dịch mới phát sinh.

## Ghi chú
Đây là dữ liệu demo. Sao kê nhập thủ công, chưa kết nối ngân hàng thật; phần chứng từ hiện ghi mã và mô tả, chưa upload file đính kèm. Đối soát dòng tiền không thay thế báo cáo doanh thu kế toán.


## Luồng nhắc Quản lý quá hạn
1. Nhân viên trình báo cáo.
2. Để quá 10 phút mà Quản lý chưa duyệt.
3. Chạy `python manage.py dispatch_qt02_reminders` trong thư mục `backend`.
4. Đăng nhập bằng tài khoản Quản lý, vào **Đối soát cuối ngày** và kiểm tra thông báo nhắc duyệt.
5. Đánh dấu thông báo đã xem. Command chỉ tạo thông báo nội bộ; để tự động hóa cần lập lịch chạy mỗi phút bằng Windows Task Scheduler.

## Kiểm tra thời điểm sao kê
1. Nhập một dòng sao kê có `transactionAt` thuộc ngày khác ngày đối soát.
2. Nhấn kiểm tra ngoại lệ.
3. Hệ thống phải tạo ngoại lệ "Sai ngày giao dịch trên sao kê".
4. Với giao dịch có thời điểm ở cả QT01 và sao kê, báo cáo hiển thị độ lệch thời gian để người kiểm tra xem xét. Do tài liệu nghiệp vụ chưa quy định ngưỡng lệch phút, hệ thống không tự đặt ngưỡng để kết luận sai.
