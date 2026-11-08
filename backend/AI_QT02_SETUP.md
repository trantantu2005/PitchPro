# PitchPro - Một chức năng AI duy nhất

**AI được giữ:** Nhân viên mở kỳ đối soát (Quy trình 02), tại phần **Chênh lệch / ngoại lệ**, tải chứng từ PDF có văn bản/TXT/CSV hoặc dán nội dung, rồi bấm **AI đọc chứng từ và gợi ý nguyên nhân**.

- API: `POST /api/reconciliation/{day}/exceptions/{exception_id}/ai/`
- Xử lý: `backend/process_2/views.py::ai_analyze_exception` và `backend/process_2/ai_service.py`
- Lưu lịch sử: `process_2.ReconciliationAIAnalysis` với `analysis_type='exception'`.
- AI chỉ cung cấp nguyên nhân có thể, dữ kiện, điểm chưa chắc chắn, bước cần kiểm tra và đề xuất tham khảo. Không tự sửa số liệu, duyệt hoặc khóa sổ.

Các chức năng AI hủy sân, AI phân tích giao dịch QT01 và AI tóm tắt khoản treo QT02 đã được gỡ khỏi API và giao diện. **Hủy sân vẫn hoạt động bằng quy tắc thuần Python** tại `process_1/cancellation_rules.py` và API `POST /api/bookings/{id}/cancel/`. Quản lý xử lý tiền cọc riêng; không tự động hoàn tiền.

## Chạy ở Windows

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

## Cấu hình AI (backend, không lưu khóa trong code)

Chọn **một** provider. Ví dụ OpenAI:

```powershell
$env:QT02_AI_PROVIDER = 'openai'
$env:OPENAI_API_KEY = 'KEY_RIENG_CUA_BAN'
$env:OPENAI_MODEL = 'gpt-4.1-mini'
python manage.py runserver
```

Để chọn Gemini hoặc Ollama, xem các biến môi trường trong `process_2/ai_service.py`. Một chức năng AI có thể dùng các provider khác nhau; đây không phải ba chức năng AI.

Chứng từ tải lên có thể chứa dữ liệu nhạy cảm. Chỉ dùng chứng từ demo hoặc đã che thông tin nhạy cảm trước khi gửi tới bên cung cấp AI. Không đẩy `.env`, `backend/media/` hoặc DB thật lên Git.

Các model/migration cũ liên quan tới lịch sử AI vẫn được giữ nhằm tương thích với dữ liệu SQLite đã có; không phát sinh phân tích mới cho khoản treo.
