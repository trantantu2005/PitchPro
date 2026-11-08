@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0backend"

echo ===============================================
echo       PITCHPRO - DJANGO + SQLITE
 echo ===============================================
if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Tao moi truong Python...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Khong tim thay lenh py, thu python...
    python -m venv .venv
  )
)
if not exist ".venv\Scripts\python.exe" goto failed

echo [2/5] Cai Django va thu vien QR...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo [3/5] Tao bang va cap nhat SQLite...
".venv\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 goto failed

echo [4/5] Tao du lieu mau va tai khoan demo...
".venv\Scripts\python.exe" manage.py seed_demo
if errorlevel 1 goto failed

 echo [5/5] Mo website...
start "PitchPro Django Server" cmd /k .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000/"
echo.
echo Da mo website. Giu cua so PitchPro Django Server dang chay.
echo Neu trang khong tai, kiem tra Terminal cua server va nhan F5.
echo.
echo Nhan vien: nhanvien
 echo Quan ly : quanly
 echo Mat khau : PitchPro@2026
pause
exit /b 0

:failed
echo.
echo LOI: Chua khoi dong duoc. Kiem tra Python 3.10+ va Internet de cai goi.
echo Hay gui lai phan loi o cua so nay de duoc ho tro.
pause
exit /b 1
