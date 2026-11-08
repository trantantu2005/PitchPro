import json
import uuid
from datetime import date, time
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.db import IntegrityError
from django.http import JsonResponse
from django.utils import timezone


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def role_of(user):
    """Xac dinh vai tro tai backend; is_staff chi la quyen vao Django Admin."""
    if not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return 'Manager'
    names = set(user.groups.values_list('name', flat=True))
    # Khong cho tai khoan Customer dong thoi co quyen noi bo do gan nham Group.
    if 'Customer' in names and ('Staff' in names or 'Manager' in names):
        return None
    if 'Manager' in names:
        return 'Manager'
    if 'Staff' in names:
        return 'Staff'
    if 'Customer' in names:
        return 'Customer'
    return None


def require_role(user, *allowed):
    if role_of(user) not in allowed:
        raise ApiError('Tai khoan khong co quyen thuc hien thao tac nay.', 403)


def api(func):
    @wraps(func)
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Cần đăng nhập trước.'}, status=401)
        try:
            # TOAN BO API QT01/QT02 hien tai la API NOI BO.
            # Customer se co bo /api/customer/ rieng o giai doan 2.
            require_role(request.user, 'Staff', 'Manager')
            return func(request, *args, **kwargs)
        except ApiError as exc:
            return JsonResponse({'error': exc.message}, status=exc.status)
        except (ValueError, TypeError, KeyError, InvalidOperation, json.JSONDecodeError):
            return JsonResponse({'error': 'Dữ liệu gửi lên không hợp lệ.'}, status=400)
        except IntegrityError:
            return JsonResponse({'error': 'Dữ liệu trùng hoặc xung đột; vui lòng tải lại.'}, status=409)
    return inner


def data(request):
    if request.content_type != 'application/json':
        raise ApiError('Yêu cầu có Content-Type: application/json.', 415)
    if int(request.META.get('CONTENT_LENGTH') or 0) > 1_000_000:
        raise ApiError('Dữ liệu vượt giới hạn 1 MB.', 413)
    try:
        obj = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        raise ApiError('JSON không hợp lệ.')
    if not isinstance(obj, dict):
        raise ApiError('Nội dung phải là JSON object.')
    return obj


def require_method(request, *methods):
    if request.method not in methods:
        raise ApiError('Phương thức HTTP không hợp lệ.', 405)


def amount(value, *, allow_zero=True, allow_negative=False):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ApiError('Số tiền không hợp lệ.')
    if not number.is_finite() or number != number.to_integral_value() or abs(number) > 100_000_000_000:
        raise ApiError('Số tiền phải là số nguyên VNĐ hợp lệ.')
    if not allow_negative and number < 0:
        raise ApiError('Số tiền không được âm.')
    if not allow_zero and number == 0:
        raise ApiError('Số tiền phải lớn hơn 0.')
    return number


def as_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ApiError('Ngày không hợp lệ. Dùng định dạng YYYY-MM-DD.')


def as_time(value):
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ApiError('Giờ không hợp lệ.')


def ref():
    return uuid.uuid4().hex[:18].upper()


def log(user, event, detail):
    from operations.models import AuditLog
    AuditLog.objects.create(actor=user, event=event, detail=detail)


def staff_manager(user):
    require_role(user, 'Manager')


def ensure_unlocked(day):
    # QT01 chỉ cần biết kỳ nào đã khóa; không phụ thuộc vào cấu trúc model QT02.
    from process_2.models import ReconciliationSession
    from operations.models import Reconciliation as LegacyReconciliation
    is_locked = (
        ReconciliationSession.objects.filter(day=day, status='locked').exists()
        or LegacyReconciliation.objects.filter(day=day, status='locked').exists()
    )
    if is_locked:
        raise ApiError('Ngày kinh doanh này đã khóa sổ.', 409)
