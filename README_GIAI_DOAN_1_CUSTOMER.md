# PITCHPRO - GIAI DOAN 1: VAI TRO CUSTOMER VA KHOA QUYEN NOI BO

## Da thay doi

- `Customer.user` (OneToOne → `auth_user`, cho phep `NULL`) de giu nguyen khach cu chua co tai khoan.
- Migration `operations/migrations/0002_customer_user.py` (KHONG sua migration 0001 da co).
- Tao ba Django Groups: `Staff`, `Manager`, `Customer` trong lenh `seed_demo`.
- Seed tai khoan demo `khachhang` va ho so Customer rieng; gan `nhanvien` vao `Staff`.
- Toan bo API QT01 va QT02 dung chung bo kiem tra `@api` de **chi Staff/Manager** truy cap.
- `employee_required` QT02 yeu cau dung nhom `Staff`; `staff_manager` yeu cau `Manager`.
- API `/api/session/` tra them `role` (giup giai doan 2 hien thi giao dien dung vai tro).
- Trong DEBUG, chung tu tai len `media/` khong con duoc mo cong khai; chi Staff/Manager xem duoc.
- Them kiem thu phan quyen cho Customer, Staff, Manager va phien dang nhap chua duoc phan vai tro.

## Chua lam o giai doan 1

- Chua co giao dien Customer va API tu dat san/thanh toan. Dang nhap `khachhang` qua API session duoc, **khong the truy cap API noi bo**, dung theo thiet ke.
- Chua cho Customer tu tao tai khoan. Se lam o giai doan 2.
- Chua co thanh toan truc tuyen that / webhook ngan hang.
- Chua co co che bao ve `MEDIA_ROOT` khi trien khai production; can cho phep truy cap sau xac thuc qua app/proxy.

## Cach cai vao DU AN DANG SU DUNG tren Windows (khong mat DB)

1. **Sao luu** `backend/db.sqlite3` truoc khi cap nhat.
2. Thay nhung file code co trong `PitchPro_GiaiDoan1_ChiFileSua.zip` vao dung duong dan tuong ung; KHONG copy `db.sqlite3` cua ban khac de ghi de DB hien tai.
3. Mo PowerShell tai thu muc `backend` va kich hoat venv du an (hoac su dung `.venv\Scripts\python.exe`):

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py test operations process_2
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Neu chua co `.venv` thi tao `py -m venv .venv` va `pip install -r requirements.txt` truoc.

**Quan trong:** Tat ca tai khoan nhan vien da tao truoc phai duoc gan vao Group `Staff`; tai khoan quan ly vao `Manager`. Lenh `seed_demo` tu gan cho 2 tai khoan mau `nhanvien` va `quanly`, KHONG tu gan cho moi user cu khac. Co the gan Group trong `/admin/` bang tai khoan quan ly.

## Bang kiem tra nhanh

| Tai khoan | URL | Ket qua mong doi |
|---|---|---|
| Chua dang nhap | `GET /api/state/` | HTTP 401 |
| `nhanvien` (Staff) | `GET /api/state/` | HTTP 200 |
| `quanly` (Manager) | `GET /api/state/` | HTTP 200 |
| `khachhang` (Customer) | `GET /api/state/` | HTTP 403 |
| `khachhang` (Customer) | `GET /api/reconciliation/` | HTTP 403 |
| `khachhang` (Customer) | `POST /api/invoices/1/pay/` | HTTP 403 |

Tai khoan demo: `nhanvien`, `quanly`, `khachhang`; mat khau do `seed_demo` tao **chi voi tai khoan moi**: `PitchPro@2026`. Khong dung mat khau demo tren he thong that.

## ERD can cap nhat

Bo sung `Customer.user_id` la FK UNIQUE, NULLABLE → `auth_user.id` (One-to-zero-or-one). Nhung Customer hien co co `user_id = NULL` cho den khi xac minh va lien ket tai khoan. Cac quan he Customer–Booking–Invoice–Payment cu khong thay doi.

## Bao cao 3.3.2 (goi y)

Hien tai 3 Group: Customer, Staff, Manager. Customer duoc xac thuc qua `/api/session/` nhung chua co chuc nang dat san tu phuc vu; backend ngan truy cap toan bo API noi bo cua QT01 va QT02. Staff thuc hien nghiep vu dat san, thanh toan va doi soat; Manager duyet ngoai le, bao cao, khoa so. Bang phan quyen phai phan biet **quyen da lam** va **quyen du kien cho giai doan 2**.
