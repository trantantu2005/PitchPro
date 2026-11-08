# PitchPro – Hệ thống Quản lý và Đặt sân bóng

**Đồ án phát triển hệ thống thông tin quản lý (MIS)**

Ứng dụng web hỗ trợ vận hành sân bóng, quản lý đặt sân, dịch vụ, thanh toán và đối soát doanh thu cuối ngày.

**Công nghệ:** Python · Django 5.2 · SQLite · HTML · CSS · JavaScript

**Phạm vi:** Dự án học tập, chạy và trình diễn trên môi trường cục bộ; chưa phải sản phẩm triển khai thương mại.

---

## 1. Giới thiệu dự án

**PitchPro** được xây dựng nhằm số hóa hai nhóm hoạt động có liên hệ với nhau trong quá trình vận hành sân bóng:

- **Quy trình 01 – Xử lý dịch vụ và thanh toán:** Từ đặt sân, nhận/trả sân, cung cấp dịch vụ đến lập hóa đơn và ghi nhận giao dịch.
- **Quy trình 02 – Tổng hợp và đối soát doanh thu cuối ngày:** Sử dụng dữ liệu giao dịch từ Quy trình 01 để kiểm quỹ, đối chiếu sao kê, xác định ngoại lệ, giải trình, phê duyệt và khóa sổ.

Hai quy trình nằm trong **một hệ thống, sử dụng chung cơ sở dữ liệu**, đồng thời được tổ chức thành các module nghiệp vụ riêng để thuận tiện phát triển và bảo trì.

## 2. Công nghệ sử dụng

| Thành phần | Công nghệ / giải pháp |
| --- | --- |
| Backend | Python, Django (`>=5.2,<5.3`) |
| Frontend | HTML, CSS, JavaScript |
| Cơ sở dữ liệu | SQLite, Django ORM |
| Xác thực và phân quyền | Django Authentication, Groups |
| Mã QR demo | Thư viện `qrcode` |
| Đọc chứng từ PDF | Thư viện `pypdf` |
| AI hỗ trợ đối soát | Gemini, OpenAI hoặc Ollama |
| Phân tích nghiệp vụ | Tài liệu quy trình, mô hình dữ liệu, kịch bản kiểm thử |

## 3. Các chức năng chính

### 3.1. Đăng nhập chung và phân quyền

Hệ thống sử dụng một cổng đăng nhập chung và phân quyền theo ba vai trò:

| Vai trò | Chức năng |
| --- | --- |
| Customer – Khách hàng | Đăng ký, đăng nhập, xem sân trống, đặt sân và theo dõi lịch đặt |
| Staff – Nhân viên | Quản lý đặt sân, dịch vụ, hóa đơn, thanh toán và lập đối soát |
| Manager – Quản lý | Theo dõi hoạt động, xử lý ngoại lệ, phê duyệt báo cáo và khóa sổ |

### 3.2. Quy trình 01 – Đặt sân, dịch vụ và thanh toán

- Quản lý lịch đặt sân và trạng thái sử dụng sân.
- Thực hiện nhận sân, trả sân và hủy sân theo các quy tắc nghiệp vụ.
- Quản lý hàng hóa, dịch vụ, số lượng tồn kho và nhập kho.
- Lập hóa đơn, bổ sung dịch vụ, ghi nhận tiền cọc và thanh toán.
- Hỗ trợ tạo mã QR phục vụ mô phỏng thanh toán.
- Cho phép khách hàng tự đặt sân qua giao diện riêng.

Hệ thống chưa tích hợp đầy đủ thanh toán ngân hàng trực tuyến thực tế.

### 3.3. Quy trình 02 – Đối soát doanh thu cuối ngày

- Tổng hợp các giao dịch thanh toán thành công.
- Phân tách giao dịch tiền mặt và chuyển khoản.
- Nhập số tiền kiểm quỹ và dữ liệu sao kê ngân hàng mô phỏng.
- Đối chiếu số tiền, mã tham chiếu và thời điểm giao dịch.
- Phát hiện các trường hợp chênh lệch, thiếu hoặc sai thông tin.
- Hỗ trợ nhân viên giải trình và đề xuất phương án xử lý.
- Quản lý xem xét ngoại lệ, phê duyệt báo cáo và khóa sổ.
- Hỗ trợ lưu lịch sử, xuất báo cáo CSV và thông báo nhắc duyệt nội bộ.

### 3.4. AI hỗ trợ phân tích chênh lệch doanh thu

PitchPro hiện tích hợp **một chức năng AI trong Quy trình 02**, có nhiệm vụ hỗ trợ nhân viên phân tích ngoại lệ đối soát.

AI có thể sử dụng nội dung chứng từ PDF có lớp văn bản, TXT, CSV hoặc thông tin nhân viên cung cấp để:

- Gợi ý những nguyên nhân có thể gây chênh lệch.
- Xác định dữ kiện hỗ trợ và thông tin còn thiếu.
- Đề xuất các bước cần kiểm tra.
- Hỗ trợ soạn nội dung giải trình tham khảo.

**AI không tự động sửa số liệu, thực hiện thanh toán, phê duyệt báo cáo hoặc khóa sổ.** Những quyết định nghiệp vụ vẫn do nhân viên và quản lý thực hiện.

## 4. Cấu trúc mã nguồn

```text
PitchPro/
├── auth.html
├── customer.html
├── index.html
├── assets/
│   ├── css/
│   └── js/
├── backend/
│   ├── manage.py
│   ├── config/
│   ├── operations/
│   ├── process_1/
│   ├── process_2/
│   ├── shared/
│   └── requirements.txt
├── docs/
├── CHAY_WINDOWS.bat
└── README.md
```

**Giải thích các thành phần chính:**

- `operations/`: Quản lý dữ liệu nghiệp vụ dùng chung.
- `process_1/`: Xử lý đặt sân, dịch vụ và thanh toán.
- `process_2/`: Xử lý đối soát, ngoại lệ, báo cáo và AI hỗ trợ.
- `shared/`: Các tiện ích API, phân quyền và xử lý dữ liệu dùng chung.
- `assets/`: Giao diện CSS và JavaScript.
- `docs/`: Tài liệu nghiệp vụ và kịch bản kiểm thử.

## 5. Hướng dẫn cài đặt và chạy

**Yêu cầu:** Python tương thích Django 5.2, pip, Windows và PowerShell.

### Cách 1: Chạy nhanh

Tại thư mục gốc dự án, nhấp đúp:

`CHAY_WINDOWS.bat`

Script hỗ trợ thiết lập môi trường, cài thư viện, thực hiện migration, tạo dữ liệu demo và khởi động Django.

**Lưu ý:** Sao lưu `backend/db.sqlite3` nếu đang có dữ liệu riêng trước khi chạy script tạo dữ liệu mẫu.

### Cách 2: Chạy bằng PowerShell

Mở Terminal tại thư mục gốc dự án:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Truy cập:

`http://127.0.0.1:8000/`

### Cấu hình AI với Gemini (tùy chọn)

Trong Terminal dùng để chạy Django:

```powershell
$env:QT02_AI_PROVIDER = "gemini"
$env:GEMINI_API_KEY = Read-Host "Nhap Gemini API Key"
$env:GEMINI_MODEL = "gemini-3.1-flash-lite"
```

Sau đó khởi động Django trong cùng Terminal. Model cần phù hợp với quyền truy cập API của người sử dụng.

Không công khai API key hoặc chứng từ chứa dữ liệu nhạy cảm.

## 6. Kiểm thử hệ thống

Mã nguồn có các bài kiểm thử Django liên quan đến:

- Đặt sân, dịch vụ và thanh toán.
- Xác thực và phân quyền người dùng.
- Xử lý ngoại lệ trong đối soát doanh thu.
- Kiểm tra dữ liệu sao kê và thông tin giao dịch.
- Phê duyệt, khóa sổ và bảo toàn dữ liệu báo cáo.
- Các thành phần tích hợp AI trong phạm vi kiểm thử.

**Lệnh kiểm thử:**

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test operations process_1 process_2
```

Nội dung README được tổng hợp từ mã nguồn và tài liệu đi kèm. Kết quả chạy toàn bộ bộ kiểm thử trên một môi trường mới cần được xác nhận riêng.

## 7. Vai trò và đóng góp cá nhân

**Vai trò:** Full-stack Developer & System Analyst – Phụ trách toàn bộ quá trình phân tích, thiết kế, phát triển và hoàn thiện hệ thống PitchPro.

### 7.1. Phân tích và thiết kế hệ thống
- Phân tích yêu cầu và xây dựng các quy trình nghiệp vụ quản lý đặt sân, dịch vụ, thanh toán và đối soát doanh thu cuối ngày.
- Mô hình hóa quy trình nghiệp vụ bằng BPMN, phân tích và đề xuất cải tiến quy trình.
- Thiết kế sơ đồ thực thể – liên kết (ERD), xác định các bảng dữ liệu, khóa chính, khóa ngoại và mối quan hệ trong hệ thống.
- Xây dựng cấu trúc cơ sở dữ liệu phục vụ hai quy trình nghiệp vụ trên cùng một hệ thống.

### 7.2. Phát triển ứng dụng web
- Xây dựng ứng dụng web bằng Python và Django, kết hợp HTML, CSS và JavaScript để phát triển giao diện người dùng.
- Triển khai các chức năng quản lý đặt sân, nhận/trả sân, hủy sân, dịch vụ, hàng hóa, hóa đơn và thanh toán.
- Xây dựng chức năng tổng hợp giao dịch, đối soát doanh thu, phát hiện chênh lệch và quản lý báo cáo cuối ngày.
- Thiết lập xác thực, đăng nhập và phân quyền theo ba vai trò: Customer, Staff và Manager.
- Xử lý các nghiệp vụ và kết nối dữ liệu giữa Frontend, Backend và cơ sở dữ liệu SQLite.

### 7.3. Tích hợp AI hỗ trợ nghiệp vụ
- Tích hợp chức năng AI hỗ trợ phân tích nguyên nhân chênh lệch doanh thu trong quy trình đối soát.
- Xây dựng luồng tiếp nhận thông tin, gửi yêu cầu tới mô hình AI và hiển thị kết quả gợi ý cho người dùng.
- Đảm bảo AI đóng vai trò hỗ trợ phân tích, không tự động thay đổi số liệu hoặc thực hiện các quyết định phê duyệt.

### 7.4. Kiểm thử và hoàn thiện
- Thực hiện kiểm thử các chức năng và luồng nghiệp vụ của hệ thống.
- Phát hiện, phân tích và khắc phục lỗi trong quá trình phát triển.
- Kiểm tra tính nhất quán dữ liệu giữa các module và hoàn thiện chức năng theo yêu cầu nghiệp vụ.
- Xây dựng tài liệu mô tả hệ thống, quy trình nghiệp vụ và hướng dẫn sử dụng.

### 7.5. Kỹ năng và kinh nghiệm tích lũy

- **Backend Development:** Python, Django, Django ORM.
- **Frontend Development:** HTML, CSS, JavaScript.
- **Database Design:** SQLite, SQL, ERD.
- **Business & System Analysis:** BPMN, phân tích và thiết kế hệ thống thông tin.
- **AI Integration:** Tích hợp API AI hỗ trợ quy trình nghiệp vụ.
- **Software Testing:** Kiểm thử chức năng, phân tích và xử lý lỗi.
- **Problem Solving:** Phân tích yêu cầu, giải quyết vấn đề và hoàn thiện sản phẩm phần mềm.
## 8. Giới hạn và lưu ý

- PitchPro là nguyên mẫu phục vụ mục đích học tập và trình diễn.
- SQLite phù hợp môi trường demo, cần đánh giá lại khi triển khai nhiều người sử dụng đồng thời.
- Dữ liệu sao kê ngân hàng được nhập theo hình thức thủ công hoặc mô phỏng.
- Chức năng AI cần cấu hình provider hợp lệ để hoạt động.
- Không sử dụng mật khẩu demo trong môi trường công khai.
- Không công khai API key, dữ liệu khách hàng, chứng từ thật hoặc cơ sở dữ liệu chứa thông tin riêng tư.
- Việc chia sẻ mã nguồn đồ án nhóm cần có sự đồng thuận của các thành viên liên quan.

---

*PitchPro – Đồ án phát triển hệ thống thông tin quản lý.*
