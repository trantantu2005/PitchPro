> **Cập nhật mới:** Sau Giai đoạn 2, PitchPro sử dụng **một trang đăng nhập chung tại `/`** (xem `README_DANG_NHAP_CHUNG.md`). Các mô tả “chuyển từ trang quản lý sang trang khách” dưới đây chỉ là cách hoạt động của phiên bản cũ và không còn áp dụng.

# PITCHPRO - GIAI DOAN 2: KHACH HANG TU DAT SAN

Ban nay **bat buoc duoc cai tren Giai doan 1** (3 Django Groups + `Customer.user` + migration `0002_customer_user.py`).

## Da thuc hien

- Trang rieng **`http://127.0.0.1:8000/khach/`**, khong hien bang dieu khien/quyen noi bo cho Customer.
- Khach **dang ky** (username + ho ten + SDT + mat khau), dang nhap va dang xuat.
- Tu dong **chuyen huong Customer tu trang dang nhap quan ly `/` sang `/khach/`**.
- Xem danh sach san dang hoat dong, gia theo gio va khung gio da co lich (chi hien gio, khong lo thong tin khach khac).
- Khach chon san, ngay, gio -> backend kiem tra khung gio -> tao **Booking + Invoice + InvoiceLine** trong DB chung; gia san duoc tinh tren server.
- Khach xem **lich cua minh**. API Customer chi tra du lieu theo `request.user.customer_profile`, khong tin `customerId` tu browser.
- Khach KHONG duoc tu thu coc / xac nhan chuyen khoan, khong xem duoc `/api/state/`, thanh toan, kho, doi soat.
- Them cac bai test tu dong cho vai tro, tranh lo thong tin, dat trung lich, gia/chung tu, dang ky va gioi han.

## Chua co trong Giai doan 2

- Chua co thanh toan/coc truc tuyen: tuy `deposit_percent=40` (de du kien), **Payment CHUA duoc tao** va hoa don van `draft`. Khong duoc trinh bay 'khach da dat coc'.
- Chua co khach tu huy / hoan tien. Se lam sau khi hoan thien chinh sach huy va thanh toan (GD3).
- Moi khach gioi han toi da 3 lich chua hoan tat trong ban demo, nhung chua co han giu suat tu dong. Nen ket hop quy dinh qua han chua coc voi GD3.
- Khong dung ban demo de nhan thanh toan that. Dang ky khach chua co xac minh SDT/OTP, chong spam/chong bot.
- SQLite phu hop demo cuc bo, **khong dam bao tuong tranh cho dat san dong thoi tren nhieu may**. Deploy that nen dung PostgreSQL + rang buoc chong chong lich giao dich.

## Tai ve/cap nhat KHONG mat database

1. **Sao luu** `backend/db.sqlite3` vao cho khac.
2. Giai nen ZIP **chi file sua** vao dung thu muc goc `PitchPro_Tinh_Gon_1_AI`, cho phep ghi de code. **Khong copy DB tu ZIP nao**.
3. PowerShell trong `backend`:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py migrate
python manage.py seed_demo
python manage.py test operations process_2 process_1.test_customer
python manage.py runserver 127.0.0.1:8000
```

Giai doan 2 khong them truong CSDL moi so voi GD1; **khong can `makemigrations`** neu da co migration `0002_customer_user.py`.

4. Mo:
- `http://127.0.0.1:8000/khach/` (khach hang)
- `http://127.0.0.1:8000/` (nhan vien / quan ly)

Tai khoan demo `khachhang`, mat khau `PitchPro@2026` chi duoc tao khi tai khoan chua ton tai; neu mat khau da bi thay thi giu nguyen mat khau hien tai.

## API bo sung (Customer)

| Phuong thuc | Duong dan | Mo ta |
|---|---|---|
| POST | `/api/customer/register/` | Dang ky tu do, phan Group Customer |
| GET | `/api/customer/fields/` | Danh muc san dang hoat dong, thong tin cua chinh minh |
| GET | `/api/customer/availability/?date=YYYY-MM-DD&fieldId=1` | Cac khoang gio da chiem, khong hien thong tin khach khac |
| GET | `/api/customer/availability/?date=...&fieldId=...&start=17:00&end=18:30` | Kiem tra khung gio cu the, `available: true/false` |
| GET | `/api/customer/bookings/` | 100 lich gan nhat cua chinh minh |
| POST | `/api/customer/bookings/` | Tao Booking + Invoice nhap + tien san, KHONG tao Payment |

## Cac file thay doi

- **Moi:** `customer.html`, `assets/css/customer.css`, `assets/js/customer.js`, `backend/process_1/customer_views.py`, `backend/process_1/customer_urls.py`, `backend/process_1/test_customer.py`.
- **Sua:** `backend/config/urls.py`, `assets/js/app.js`, `index.html` (doi query version JS).
- **Khong sua:** `operations/models.py`, `operations/migrations/*`, `process_2/*`, CSDL cu.

## Cap nhat bao cao MIS3047

- **3.3.2:** them Customer, trang `/khach/`, quyen xem san, dat va xem lich rieng.
- **3.3.3:** User Task - chon san/nhap ngay gio/tu dat; Service Task - kiem tra xung dot, tinh tien san, tao Invoice; XOR - con san?; Lane - Customer va Staff.
- **3.3.5:** Phan tach API khach va API noi bo, lien ket `Customer.user_id` (da bo sung GD1), khong thu tien khi chua xac minh.
- **2.4 (To-Be QT01):** mo rong Lane Khach hang; QT02 khong them Lane Customer.
- **4.1, 4.3:** minh chung 3 vai tro, API moi, kiem thu phan quyen + trung lich + thanh toan chua ghi nhan.

## Gioi han kiem thu trong moi truong tao file

Da kiem tra cu phap Python va co the kiem tra JavaScript neu may co Node.js, NHUNG moi truong xuat file khong co Django va khong co Internet de cai dependency; do do **chua xac nhan test Django pass**. Hay chay `python manage.py check` va `python manage.py test ...` tren may Windows truoc khi dung de demo.
