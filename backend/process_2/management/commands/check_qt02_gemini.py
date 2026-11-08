"""Công cụ kiểm tra Gemini API QT02; không in khóa API hoặc sửa CSDL."""
from django.core.management.base import BaseCommand, CommandError
from process_2.ai_service import (
    AIServiceError, _call_gemini, _gemini_model_name, list_gemini_models
)


class Command(BaseCommand):
    help = 'Kiểm tra tên model Gemini và thử AI QT02 mà không sửa dữ liệu kinh doanh.'

    def add_arguments(self, parser):
        parser.add_argument('--list', action='store_true', help='Liệt kê model hỗ trợ generateContent.')
        parser.add_argument('--smoke', action='store_true', help='Gọi Gemini thật bằng dữ liệu giả lập.')

    def handle(self, *args, **options):
        try:
            model = _gemini_model_name()
            self.stdout.write(f'Model cấu hình: {model}')
            if options['list'] or not options['smoke']:
                names = list_gemini_models()
                self.stdout.write('Model có generateContent cho API key hiện tại:')
                for name in names:
                    self.stdout.write('  ' + name + ('  [ĐANG CHỌN]' if name == model else ''))
                if model not in names:
                    self.stdout.write(self.style.WARNING(
                        'Model đang chọn không có trong danh sách; hãy chọn một tên bên trên.'))
                else:
                    self.stdout.write('Model đang chọn có trong danh sách (chưa xác nhận gọi sinh nội dung).')
            if options['smoke']:
                suggestion, actual = _call_gemini(
                    'Kiểm thử kết nối: phân tích ngoại lệ thiếu tiền mặt của PitchPro.',
                    {
                        'businessDay': '2026-11-02',
                        'exception': {
                            'category': 'Thiếu tiền mặt',
                            'amountDifference': -10000,
                            'description': 'Dữ liệu DEMO: dự kiến 250000 VNĐ, thực kiểm 240000 VNĐ.',
                        },
                        'instruction': 'Chỉ ghi nhận chênh lệch và gợi ý xác minh; không tự phê duyệt.',
                    },
                )
                self.stdout.write(self.style.SUCCESS(f'GỌI AI THÀNH CÔNG - {actual}'))
                self.stdout.write('Tóm tắt: ' + suggestion['summary'][:500])
        except AIServiceError as exc:
            raise CommandError(str(exc)) from None
