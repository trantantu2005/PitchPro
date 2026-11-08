# Quy trình 1 – Dịch vụ & thanh toán

Module này sở hữu API nghiệp vụ:
- Đặt sân, nhận sân, trả sân.
- Hóa đơn, dòng hóa đơn, bán sản phẩm/dịch vụ.
- Thu cọc, tạo QR demo, xác nhận thanh toán.
- Quản lý kho và nhập kho.

Các entity dùng chung hiện đặt tại `operations/models.py`.
Quy trình 1 ghi nhận giao dịch `Payment`; QT02 đọc các payment đã xác nhận.
Không chuyển logic đối soát sang module này.
