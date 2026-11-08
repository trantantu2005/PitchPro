"""Cong khach hang QT01 (Giai doan 2) - tach hoan toan API quan ly noi bo.

Chuc nang: dang ky, xem san trong, tu dat san, xem lich cua chinh minh.
Chua thu tien coc/QR; moi lich tao o trang thai BOOKED, hoa don DRAFT.
"""
import json
import re
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group
from django.db import IntegrityError, OperationalError, transaction
from django.http import JsonResponse
from django.utils import timezone

from operations.models import Booking, Customer, FootballField, Invoice, InvoiceLine
from shared.api import ApiError, as_date, as_time, data, ensure_unlocked, log, require_method, role_of


DEPOSIT_RATE = 40  # Du kien ty le coc; giai doan 2 KHONG ghi nhan da thu coc.
MAX_FUTURE_BOOKINGS = 3  # Gioi han tam thoi tranh giu qua nhieu suat tren demo.


def customer_api(fn):
    @wraps(fn)
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Vui lòng đăng nhập để đặt sân.'}, status=401)
        if role_of(request.user) != 'Customer':
            return JsonResponse({'error': 'Chức năng này chỉ dành cho Khách hàng.'}, status=403)
        try:
            return fn(request, *args, **kwargs)
        except ApiError as exc:
            return JsonResponse({'error': exc.message}, status=exc.status)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Dữ liệu gửi lên không hợp lệ.'}, status=400)
        except IntegrityError:
            return JsonResponse({'error': 'Dữ liệu trùng hoặc xung đột, vui lòng thử lại.'}, status=409)
        except OperationalError:
            return JsonResponse({'error': 'Đang có lượt đặt đồng thời. Vui lòng thử lại.'}, status=409)
    return inner


def _profile(user):
    profile = Customer.objects.filter(user=user).first()
    if not profile:
        raise ApiError('Tài khoản chưa có hồ sơ khách hàng. Vui lòng liên hệ nhân viên.', 409)
    return profile


def _validate_slot(day, start, end):
    today = timezone.localdate()
    if day < today or day > today + timedelta(days=60):
        raise ApiError('Chỉ nhận lịch từ hôm nay đến 60 ngày tiếp theo.')
    if not (start < end):
        raise ApiError('Giờ kết thúc phải sau giờ bắt đầu.')
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if start.second or end.second or start.minute not in (0, 30) or end.minute not in (0, 30):
        raise ApiError('Giờ đặt phải theo mốc 30 phút.')
    if start_minutes < 6 * 60 or end_minutes > 23 * 60 or not 30 <= end_minutes - start_minutes <= 180:
        raise ApiError('Đặt từ 06:00–23:00, mỗi lượt từ 30 đến 180 phút.')
    now = timezone.localtime().time().replace(tzinfo=None)
    if day == today and start <= now:
        raise ApiError('Không thể đặt sân vào thời gian đã qua.')


def _conflicts(field, day, start, end):
    """Lay gio bi chiem, KHONG tra ten/SDT cua khach khac."""
    busy = []
    q = Booking.objects.filter(field=field, day=day).exclude(
        status=Booking.Status.CANCELLED
    ).filter(start_time__lt=end, end_time__gt=start)
    for bk in q:
        occupied_until = bk.end_time
        if bk.status == Booking.Status.COMPLETED and bk.returned_at:
            returned = timezone.localtime(bk.returned_at).time().replace(tzinfo=None)
            occupied_until = min(occupied_until, returned)
        if bk.start_time < end and occupied_until > start:
            busy.append((bk.start_time, occupied_until))
    return busy


def _booking_info(bk):
    inv = bk.invoice
    return {
        'id': bk.pk,
        'fieldName': bk.field.name,
        'fieldType': bk.field.field_type,
        'date': bk.day.isoformat(),
        'start': bk.start_time.strftime('%H:%M'),
        'end': bk.end_time.strftime('%H:%M'),
        'status': bk.status,
        'invoiceId': inv.pk,
        'invoiceStatus': inv.status,
        'total': int(inv.total),
        'collected': int(inv.collected),
        'due': int(inv.due),
        'depositRate': bk.deposit_percent,
    }


def register(request):
    """Chi anonymous duoc dang ky; khong cho phep lay quyen voi profile SDT da ton tai."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Chỉ chấp nhận POST.'}, status=405)
    if request.user.is_authenticated:
        return JsonResponse({'error': 'Hãy đăng xuất trước khi đăng ký tài khoản khác.'}, status=409)
    try:
        d = data(request)
        username = str(d.get('username', '')).strip()
        name = str(d.get('name', '')).strip()
        phone = str(d.get('phone', '')).strip()
        password = d.get('password', '')
        if not (re.fullmatch(r'[A-Za-z0-9_.-]{4,30}', username)):
            raise ApiError('Tên đăng nhập 4–30 ký tự, chỉ chữ cái, số, gạch dưới hoặc dấu chấm.')
        if not 2 <= len(name) <= 150:
            raise ApiError('Họ tên cần từ 2 đến 150 ký tự.')
        if not re.fullmatch(r'0\d{9}', phone):
            raise ApiError('Số điện thoại gồm 10 chữ số và bắt đầu bằng 0.')
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise ApiError('Mật khẩu phải từ 10 đến 128 ký tự.')
        User = get_user_model()
        with transaction.atomic():
            if User.objects.filter(username__iexact=username).exists():
                raise ApiError('Tên đăng nhập đã tồn tại.', 409)
            if Customer.objects.filter(phone=phone).exists():
                raise ApiError('Số điện thoại đã tồn tại; liên hệ nhân viên để xác minh và liên kết.', 409)
            group, _ = Group.objects.get_or_create(name='Customer')
            user = User.objects.create_user(username=username, password=password, first_name=name[:150])
            user.groups.add(group)
            Customer.objects.create(user=user, name=name, phone=phone)
        login(request, user)
        log(user, 'customer.register', 'Khach hang dang ky tai khoan tu phuc vu')
        return JsonResponse({'ok': True, 'role': 'Customer', 'username': user.username}, status=201)
    except ApiError as exc:
        return JsonResponse({'error': exc.message}, status=exc.status)
    except (IntegrityError, OperationalError):
        return JsonResponse({'error': 'Tên đăng nhập hoặc số điện thoại đã được sử dụng.'}, status=409)


@customer_api
def fields(request):
    require_method(request, 'GET')
    profile = _profile(request.user)
    items = [
        {'id': f.pk, 'name': f.name, 'type': f.field_type, 'hourlyRate': int(f.hourly_rate)}
        for f in FootballField.objects.filter(is_active=True).order_by('id')
    ]
    return JsonResponse({
        'fields': items, 'today': timezone.localdate().isoformat(),
        'customer': {'name': profile.name, 'phone': profile.phone},
        'notice': 'Giai doan 2: lich dat duoc ghi nhan, CHUA thu coc hay thanh toan truc tuyen.',
    })


@customer_api
def availability(request):
    require_method(request, 'GET')
    _profile(request.user)
    day = as_date(request.GET.get('date'))
    if day < timezone.localdate() or day > timezone.localdate() + timedelta(days=60):
        raise ApiError('Chỉ xem lịch trong 60 ngày tới.')
    try:
        field_id = int(request.GET.get('fieldId', '0'))
    except (TypeError, ValueError):
        raise ApiError('Sân không hợp lệ.')
    field = FootballField.objects.filter(pk=field_id, is_active=True).first()
    if not field:
        raise ApiError('Không tìm thấy sân đang hoạt động.', 404)
    # Ngay chi tra khung gio ban, khong tiet lo Customer co lich dat.
    existing = Booking.objects.filter(field=field, day=day).exclude(status='cancelled').order_by('start_time')
    busy = []
    for bk in existing:
        occupied_until = bk.end_time
        if bk.status == Booking.Status.COMPLETED and bk.returned_at:
            returned = timezone.localtime(bk.returned_at).time().replace(tzinfo=None)
            occupied_until = min(occupied_until, returned)
        if occupied_until > bk.start_time:
            busy.append({'start': bk.start_time.strftime('%H:%M'),
                         'end': occupied_until.strftime('%H:%M')})
    result = {'date': day.isoformat(), 'fieldId': field.pk, 'busy': busy}
    if request.GET.get('start') and request.GET.get('end'):
        start, end = as_time(request.GET['start']), as_time(request.GET['end'])
        _validate_slot(day, start, end)
        result['available'] = not bool(_conflicts(field, day, start, end))
    return JsonResponse(result)


@customer_api
def bookings(request):
    profile = _profile(request.user)
    if request.method == 'GET':
        q = Booking.objects.filter(customer=profile).select_related('field', 'invoice').order_by('-day', '-start_time')[:100]
        return JsonResponse({'items': [_booking_info(b) for b in q]})
    require_method(request, 'POST')
    d = data(request)
    day, start, end = as_date(d.get('date')), as_time(d.get('start')), as_time(d.get('end'))
    _validate_slot(day, start, end)
    try:
        field_id = int(d.get('fieldId', '0'))
    except (TypeError, ValueError):
        raise ApiError('Sân không hợp lệ.')
    with transaction.atomic():
        field = FootballField.objects.select_for_update().filter(pk=field_id, is_active=True).first()
        if not field:
            raise ApiError('Sân không tồn tại hoặc đã ngừng hoạt động.', 404)
        ensure_unlocked(day)
        # SQLite: yeu cau dat san dong thoi co the bi khoa; khong cam ket chong trung lich
        # manh nhu PostgreSQL exclusion constraints trong moi truong production.
        active_count = Booking.objects.filter(customer=profile, day__gte=timezone.localdate(),
                                              status__in=[Booking.Status.BOOKED, Booking.Status.USING]).count()
        if active_count >= MAX_FUTURE_BOOKINGS:
            raise ApiError('Mỗi khách chỉ được giữ tối đa 3 lịch chưa hoàn tất trong demo.', 409)
        if _conflicts(field, day, start, end):
            raise ApiError('Khung giờ này đã có người đặt. Vui lòng chọn giờ khác.', 409)
        bk = Booking.objects.create(
            customer=profile, field=field, day=day, start_time=start, end_time=end,
            status=Booking.Status.BOOKED, deposit_percent=DEPOSIT_RATE, created_by=request.user,
        )
        inv = Invoice.objects.create(booking=bk, customer=profile,
                                     customer_name=profile.name, status=Invoice.Status.DRAFT,
                                     created_by=request.user)
        minutes = end.hour * 60 + end.minute - (start.hour * 60 + start.minute)
        rental = (field.hourly_rate * Decimal(minutes) / Decimal(60)).quantize(Decimal('1'))
        InvoiceLine.objects.create(invoice=inv, kind='rental',
            description=f'Thuê {field.name} {start:%H:%M}-{end:%H:%M}', quantity=1, unit_price=rental)
        log(request.user, 'customer.booking_create', f'Khach tu dat san #{bk.pk}, hoa don #{inv.pk}; chua thu coc')
        info = _booking_info(bk)
    return JsonResponse({
        'booking': info,
        'notice': 'Đã ghi nhận lịch đặt. Chưa thanh toán tiền cọc. Vui lòng chờ hướng dẫn xác nhận từ nhân viên.',
    }, status=201)
