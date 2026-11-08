import json
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie

from operations.models import (
    AuditLog, Booking, Customer, FootballField, Invoice, InvoiceLine,
    Payment, Product, StockMovement,
)
from process_2.models import ReconciliationSession, ReconciliationException
from shared.api import (
    ApiError, api, amount, as_date, as_time, data, ensure_unlocked,
    log, ref, require_method, role_of,
)
from shared.serializers import booking_json, invoice_json
from .cancellation_rules import evaluate_cancellation, REASON_TYPES


@ensure_csrf_cookie
def session(request):
    if request.method == 'GET':
        role = role_of(request.user)
        return JsonResponse({'authenticated': request.user.is_authenticated,
                             'username': request.user.username if request.user.is_authenticated else None,
                             'role': role,
                             'manager': role == 'Manager'})
    if request.method == 'POST':
        try:
            d = data(request)
        except ApiError as e:
            return JsonResponse({'error': e.message}, status=e.status)
        user = authenticate(request, username=d.get('username', ''), password=d.get('password', ''))
        if not user or not user.is_active:
            return JsonResponse({'error': 'Tài khoản hoặc mật khẩu không đúng.'}, status=401)
        role = role_of(user)
        if role is None:
            return JsonResponse({'error': 'Tài khoản chưa được phân vai trò hợp lệ.'}, status=403)
        login(request, user)
        return JsonResponse({'ok': True, 'username': user.username, 'role': role})
    if request.method == 'DELETE':
        logout(request)
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@api
def bootstrap(request):
    require_method(request, 'GET')
    return JsonResponse({
        'fields': [{'id': f.id, 'name': f.name, 'type': str(f.field_type),
                    'hourlyRate': int(f.hourly_rate)} for f in FootballField.objects.filter(is_active=True)],
        'products': [{'id': p.id, 'name': p.name, 'price': int(p.price),
                      'stock': p.stock, 'unit': p.unit} for p in Product.objects.filter(is_active=True)],
        'user': {'username': request.user.username, 'role': role_of(request.user),
                 'manager': role_of(request.user) == 'Manager'},
    })

@api
def bookings(request):
    if request.method == 'GET':
        q = Booking.objects.select_related('customer', 'field', 'invoice').order_by('day', 'start_time')
        if request.GET.get('date'):
            q = q.filter(day=as_date(request.GET['date']))
        return JsonResponse({'items': [booking_json(b) for b in q[:500]]})
    require_method(request, 'POST')
    d = data(request)
    day, start, end = as_date(d['date']), as_time(d['start']), as_time(d['end'])
    if day < timezone.localdate() or start >= end:
        raise ApiError('Ngày/giờ đặt sân không hợp lệ.')

    # Không cho đặt sân vào thời gian đã qua
    if day == timezone.localdate() and start <= timezone.localtime().time().replace(tzinfo=None):
        raise ApiError('Không thể đặt sân vào thời gian đã qua.')

    ensure_unlocked(day)
    field = get_object_or_404(FootballField, pk=d['pitchId'], is_active=True)
    phone = str(d.get('phone', '')).strip()
    name = str(d.get('name', '')).strip()
    if not phone or not name or len(phone) > 20 or len(name) > 150:
        raise ApiError('Tên khách hàng hoặc số điện thoại không hợp lệ.')
    rate = int(d.get('depositRate', 0))
    if rate not in (0, 40, 50, 60):
        raise ApiError('Tỷ lệ cọc không hợp lệ.')
    with transaction.atomic():
        # Kiểm tra thời gian sân thực sự bị chiếm
        overlaps = Booking.objects.filter(
            field=field,
            day=day
        ).exclude(
            status=Booking.Status.CANCELLED
        ).filter(
            start_time__lt=end,
            end_time__gt=start
        )

        for existing in overlaps:
            occupied_until = existing.end_time

            # Nếu trả sân sớm, chỉ chiếm sân đến giờ trả thực tế
            if (
                existing.status == Booking.Status.COMPLETED
                and existing.returned_at
            ):
                returned_time = timezone.localtime(
                    existing.returned_at
                ).time().replace(tzinfo=None)

                occupied_until = min(
                    occupied_until,
                    returned_time
                )

            # Chặn những khung giờ còn bị chiếm
            if existing.start_time < end and occupied_until > start:
                raise ApiError(
                    'Sân đã có lịch trùng khung giờ.',
                    409
                )
        customer, _ = Customer.objects.get_or_create(phone=phone, defaults={'name': name})
        if customer.name != name:
            customer.name = name
            customer.save(update_fields=['name'])
        b = Booking.objects.create(customer=customer, field=field, day=day,
            start_time=start, end_time=end, deposit_percent=rate, created_by=request.user)
        inv = Invoice.objects.create(booking=b, customer=customer, customer_name=name, created_by=request.user)
        minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        rental = (field.hourly_rate * Decimal(minutes) / Decimal(60)).quantize(Decimal('1'))
        InvoiceLine.objects.create(invoice=inv, kind='rental', description=f'Thuê {field.name} {start:%H:%M}-{end:%H:%M}',
                                   quantity=1, unit_price=rental)
        log(request.user, 'booking.create', f'Đặt sân #{b.id}, hóa đơn #{inv.id}')
    return JsonResponse({'booking': booking_json(b), 'invoice': invoice_json(inv)}, status=201)

@api
def booking_transition(request, pk, action):
    require_method(request, 'POST')
    with transaction.atomic():
        b = get_object_or_404(Booking.objects.select_for_update().select_related('field', 'customer', 'invoice'), pk=pk)
        ensure_unlocked(b.day)
        if action in ('check-in', 'check-out') and b.day != timezone.localdate():
            raise ApiError('Chỉ thao tác nhận/trả sân trong ngày sử dụng.')
        if action == 'check-in':
            if b.status != 'booked':
                raise ApiError('Lượt không ở trạng thái đã đặt.', 409)
            right_now = timezone.localtime().time().replace(tzinfo=None)
            if right_now < b.start_time:
                raise ApiError('Chưa đến giờ nhận sân.', 409)
            if right_now >= b.end_time:
                raise ApiError('Đã qua giờ đặt sân. Vui lòng xử lý lịch quá hạn.', 409)
            b.status, b.received_at = 'using', timezone.now()
            b.save(update_fields=['status', 'received_at'])
            log(request.user, 'booking.check_in', f'Nhận sân #{b.id}')
        elif action == 'check-out':
            if b.status != 'using':
                raise ApiError('Lượt chưa nhận sân hoặc đã trả.', 409)
            if timezone.localtime().time().replace(tzinfo=None) < b.end_time:
                d = data(request)
                if d.get('earlyCheckout') is not True:
                    raise ApiError('Trả sân sớm cần xác nhận earlyCheckout=true.', 409)
            inv = b.invoice
            if inv.status != 'draft':
                raise ApiError('Hóa đơn không phải nháp.', 409)
            b.status, b.returned_at = 'completed', timezone.now()
            b.save(update_fields=['status', 'returned_at'])
            # Trả sân chỉ giải phóng sân, không đóng hóa đơn.
            # Khách vẫn có thể tiếp tục gọi nước và dịch vụ.
            log(
                request.user,
                'booking.check_out',
                f'Trả sân #{b.id}; hóa đơn #{inv.id} vẫn mở để phục vụ'
            )
        elif action == 'cancel':
            user = request.user

            allowed = role_of(user) in ('Staff', 'Manager')

            if not allowed:
                raise ApiError(
                    'Chỉ nhân viên hoặc chủ sân được hủy lịch.',
                    403
                )

            d = data(request)
            reason = str(d.get('reason') or '').strip()
            reason_type = str(
                d.get('reasonType') or 'personal'
            )

            if not 5 <= len(reason) <= 300:
                raise ApiError(
                    'Lý do hủy cần từ 5 đến 300 ký tự.'
                )

            if reason_type not in REASON_TYPES:
                raise ApiError(
                    'Loại lý do hủy không hợp lệ.'
                )

            inv = Invoice.objects.select_for_update().get(
                pk=b.invoice.pk
            )

            assessment = evaluate_cancellation(
                b, inv, reason_type
            )

            if not assessment['canCancel']:
                raise ApiError(
                    'Không thể hủy trực tiếp: '
                    + '; '.join(assessment['blockers']),
                    409
                )

            requires_refund_review = (
                assessment['depositReceivedVnd'] > 0
            )

            b.status = Booking.Status.CANCELLED
            b.save(update_fields=['status'])

            if not requires_refund_review:
                inv.status = Invoice.Status.CANCELLED
                inv.closed_at = timezone.now()
                inv.save(
                    update_fields=['status', 'closed_at']
                )

            log(
                user,
                'booking.cancel',
                f'Hủy lượt #{b.id}, hóa đơn #{inv.id}; '
                f'lý do: {reason}; '
                f'loại: {reason_type}; '
                f'điều khoản: {assessment["policyClause"]}; '
                f'cọc: {assessment["depositReceivedVnd"]}đ'
            )
        else:
            raise ApiError('Thao tác không hỗ trợ.', 404)

    result = {'booking': booking_json(b), 'invoice': invoice_json(inv if action == 'cancel' else b.invoice)}
    if action == 'cancel':
        result['requiresRefundReview'] = assessment['requiresManagerReview']
        result['policyAssessment'] = assessment
    return JsonResponse(result)


@api
def invoice_finalize(request, pk):
    """Chỉ chốt hóa đơn khi khách yêu cầu thanh toán."""
    require_method(request, 'POST')

    with transaction.atomic():
        inv = get_object_or_404(
            Invoice.objects.select_for_update().select_related('booking'),
            pk=pk
        )

        if not inv.booking_id or inv.booking.status != 'completed':
            raise ApiError('Khách chưa trả sân.', 409)

        if inv.booking.day != timezone.localdate():
            raise ApiError('Chỉ chốt hóa đơn trong ngày sử dụng.', 409)

        ensure_unlocked(inv.booking.day)

        if inv.status != 'draft':
            raise ApiError('Hóa đơn đã được chốt.', 409)

        inv.closed_at = timezone.now()

        if inv.due == 0:
            inv.status = 'paid'
            inv.paid_at = timezone.now()
        else:
            inv.status = 'awaiting'

        inv.save(update_fields=['closed_at', 'status', 'paid_at'])

        log(
            request.user,
            'invoice.finalize',
            f'Chốt hóa đơn #{inv.id}'
        )

    return JsonResponse({'invoice': invoice_json(inv)})
@api
def invoices(request):
    require_method(request, 'GET')
    q = Invoice.objects.select_related('customer', 'booking').order_by('-created_at')
    if request.GET.get('status'):
        q = q.filter(status=request.GET['status'])
    return JsonResponse({'items': [invoice_json(x) for x in q[:200]]})

@api
def invoice_detail(request, pk):
    require_method(request, 'GET')
    return JsonResponse({'invoice': invoice_json(get_object_or_404(Invoice, pk=pk))})

@api
def invoice_add_item(request, pk):
    require_method(request, 'POST')
    d = data(request)
    qty = int(d.get('quantity', 0))
    if qty <= 0 or qty > 1000:
        raise ApiError('Số lượng không hợp lệ.')
    with transaction.atomic():
        inv = get_object_or_404(Invoice, pk=pk)
        ensure_unlocked(timezone.localdate())
        b = inv.booking
        if not ((b and b.day == timezone.localdate() and b.status in ('using', 'completed') and inv.status == 'draft') or
                (b is None and inv.status == 'awaiting')):
            raise ApiError('Hóa đơn không còn mở để thêm dịch vụ.', 409)
        p = get_object_or_404(Product, pk=d['productId'], is_active=True)
        if p.tracks_stock:
            updated = Product.objects.filter(pk=p.id, stock__gte=qty).update(stock=F('stock') - qty)
            if not updated:
                raise ApiError('Không đủ số lượng tồn kho.', 409)
            p.refresh_from_db()
        line = InvoiceLine.objects.create(invoice=inv, product=p, kind='product',
            description=p.name, quantity=qty, unit_price=p.price)
        if p.tracks_stock:
            StockMovement.objects.create(product=p, invoice_line=line, delta=-qty,
                                         stock_after=p.stock, actor=request.user)
        log(request.user, 'invoice.add_item', f'{qty} × {p.name} -> hóa đơn #{inv.id}')
    return JsonResponse({'invoice': invoice_json(inv), 'stock': p.stock})

@api
def retail_sale(request):
    require_method(request, 'POST')
    d = data(request)
    qty = int(d.get('quantity', 0))
    if qty < 1 or qty > 1000:
        raise ApiError('Số lượng không hợp lệ.')
    ensure_unlocked(timezone.localdate())
    with transaction.atomic():
        p = get_object_or_404(Product, pk=d['productId'], is_active=True)
        if p.tracks_stock:
            if not Product.objects.filter(pk=p.id, stock__gte=qty).update(stock=F('stock') - qty):
                raise ApiError('Sản phẩm đã hết hoặc không đủ hàng.', 409)
            p.refresh_from_db()
        inv = Invoice.objects.create(status='awaiting', customer_name='Khách lẻ', created_by=request.user)
        line = InvoiceLine.objects.create(invoice=inv, product=p, kind='product',
            description=p.name, quantity=qty, unit_price=p.price)
        if p.tracks_stock:
            StockMovement.objects.create(product=p, invoice_line=line, delta=-qty,
                stock_after=p.stock, actor=request.user)
        log(request.user, 'invoice.retail_sale', f'Bán lẻ {qty} {p.unit} {p.name} -> hóa đơn #{inv.id}')
    return JsonResponse({'invoice': invoice_json(inv)}, status=201)

def check_payment_day(inv):
    ensure_unlocked(timezone.localdate())
    if inv.booking_id and inv.booking.day != timezone.localdate():
        raise ApiError('Lượt sân không thuộc ngày hôm nay.')

@api
def deposit(request, pk):
    require_method(request, 'POST')
    d = data(request)
    value = amount(d['amount'])
    method = d.get('method')
    reference = str(d.get('reference', '')).strip()
    if value <= 0 or method not in ('cash', 'bank') or (method == 'bank' and len(reference) < 5):
        raise ApiError('Số tiền, phương thức hoặc chứng từ cọc không hợp lệ.')
    with transaction.atomic():
        inv = get_object_or_404(Invoice, pk=pk)
        b = inv.booking
        if not b or b.status not in ('booked', 'using') or inv.status != 'draft':
            raise ApiError('Chỉ thu cọc khi lượt đặt còn hiệu lực.', 409)
        ensure_unlocked(timezone.localdate())  # Cọc lịch tương lai thu vào ngày giao dịch hiện tại
        rental = sum((x.quantity*x.unit_price for x in inv.lines.filter(kind='rental')), Decimal('0'))
        received = sum((x.amount for x in inv.payments.filter(kind='deposit', status='success')), Decimal('0'))
        if received + value > (rental*b.deposit_percent/100):
            raise ApiError('Số cọc vượt tỷ lệ đã thỏa thuận.', 409)
        p = Payment.objects.create(invoice=inv, kind='deposit', method=method,
            channel='manual', amount=value, status='success',
            request_code=ref(), bank_reference=reference if method == 'bank' else None,
            business_day=timezone.localdate(), created_by=request.user,
            confirmed_by=request.user, confirmed_at=timezone.now())
        log(request.user, 'payment.deposit', f'Cọc #{p.id}, hóa đơn #{inv.id}, {value}đ')
    return JsonResponse({'invoice': invoice_json(inv)}, status=201)

@api
def qr_create(request, pk):
    require_method(request, 'POST')
    with transaction.atomic():
        inv = get_object_or_404(Invoice, pk=pk)
        check_payment_day(inv)
        if inv.status != 'awaiting' or inv.due <= 0:
            raise ApiError('Hóa đơn không ở trạng thái chờ thanh toán.', 409)
        if inv.payments.filter(status='pending', channel='qr').exists():
            raise ApiError('Yêu cầu QR đã tồn tại.', 409)
        p = Payment.objects.create(invoice=inv, kind='settlement', method='bank',
            channel='qr', amount=inv.due, status='pending',
            request_code='QR-' + ref(), business_day=timezone.localdate(), created_by=request.user)
        inv.status = 'qr_pending'
        inv.save(update_fields=['status'])
        log(request.user, 'payment.qr_request', f'Yêu cầu QR {p.request_code} (chưa thu)')
    return JsonResponse({'paymentId': p.id, 'requestCode': p.request_code,
                         'amount': int(p.amount), 'status': p.status}, status=201)

@api
def qr_cancel(request, pk):
    require_method(request, 'POST')
    with transaction.atomic():
        inv = get_object_or_404(Invoice, pk=pk)
        check_payment_day(inv)
        if inv.status != 'qr_pending':
            raise ApiError('Không có yêu cầu QR đang chờ.', 409)
        inv.payments.filter(status='pending', channel='qr').update(status='cancelled')
        inv.status = 'awaiting'
        inv.save(update_fields=['status'])
        log(request.user, 'payment.qr_cancel', f'Hủy yêu cầu QR hóa đơn #{inv.id}')
    return JsonResponse({'invoice': invoice_json(inv)})

@api
def pay(request, pk):
    require_method(request, 'POST')
    d = data(request)
    method = d.get('method')
    bank_ref = str(d.get('bankReference', '')).strip()
    if method not in ('cash', 'bank'):
        raise ApiError('Chỉ hỗ trợ tiền mặt hoặc chuyển khoản.')
    if method == 'bank' and (len(bank_ref) < 5 or d.get('manuallyVerified') is not True):
        raise ApiError('Phải đối chiếu chứng từ ngân hàng và xác nhận thủ công.')
    with transaction.atomic():
        inv = get_object_or_404(Invoice, pk=pk)
        check_payment_day(inv)
        if (method == 'cash' and inv.status != 'awaiting') or (
            method == 'bank' and inv.status != 'qr_pending'):
            raise ApiError('Trạng thái hóa đơn không phù hợp.', 409)
        due = inv.due
        if due <= 0:
            raise ApiError('Hóa đơn không còn số tiền phải thu.', 409)
        if method == 'bank':
            p = inv.payments.filter(status='pending', channel='qr').first()
            if not p or p.amount != due:
                raise ApiError('Yêu cầu QR không phù hợp số tiền còn thu.', 409)
            p.bank_reference = bank_ref
            p.status, p.confirmed_at, p.confirmed_by = 'success', timezone.now(), request.user
            p.save(update_fields=['bank_reference', 'status', 'confirmed_at', 'confirmed_by'])
        else:
            p = Payment.objects.create(invoice=inv, kind='settlement', method='cash',
                amount=due, status='success', request_code='TM-' + ref(),
                business_day=timezone.localdate(), channel='manual', created_by=request.user,
                confirmed_by=request.user, confirmed_at=timezone.now())
        inv.status, inv.paid_at = 'paid', timezone.now()
        inv.save(update_fields=['status', 'paid_at'])
        log(request.user, 'payment.settled', f'Hóa đơn #{inv.id}, thanh toán {due}đ qua {method}')
    return JsonResponse({'invoice': invoice_json(inv), 'paymentId': p.id})

@api
def stock_restock(request):
    """Nhap kho co giao dich + nhat ky; tra ve ton moi tu SQLite."""
    require_method(request, 'POST')
    d = data(request)
    try:
        qty = int(d.get('quantity', 0))
    except (TypeError, ValueError):
        raise ApiError('So luong nhap khong hop le.')
    if qty < 1 or qty > 100000:
        raise ApiError('So luong nhap phai tu 1 den 100.000.')
    with transaction.atomic():
        p = get_object_or_404(
            Product.objects.select_for_update(),
            pk=d.get('productId'), is_active=True,
        )
        if not p.tracks_stock:
            raise ApiError('Day la dich vu khong theo doi ton kho. Hay chon hang hoa.', 409)
        Product.objects.filter(pk=p.pk).update(stock=F('stock') + qty)
        p.refresh_from_db(fields=['stock'])
        StockMovement.objects.create(
            product=p, delta=qty, stock_after=p.stock, actor=request.user,
        )
        log(request.user, 'stock.restock', f'Nhap them {qty} {p.unit} {p.name}')
    return JsonResponse({'ok': True, 'productId': p.id, 'product': p.name,
                         'quantity': qty, 'stock': p.stock})


@api
def qr_image(request, pk):
    require_method(request, 'GET')
    inv = get_object_or_404(Invoice, pk=pk)
    if inv.status != 'qr_pending':
        raise ApiError('Hóa đơn chưa tạo yêu cầu QR.', 409)
    p = inv.payments.filter(status='pending', channel='qr').first()
    if not p:
        raise ApiError('Không tìm thấy QR đang chờ.', 404)
    # Mã QR chứa THÔNG TIN THAM CHIẾU, không phải VietQR ngân hàng.
    import io
    import qrcode
    import qrcode.image.svg
    payload = f'PITCHPRO-DEMO|{p.request_code}|{int(p.amount)}VND'
    result = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    result.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type='image/svg+xml')
    response['Cache-Control'] = 'no-store'
    return response


@api
def state_snapshot(request):
    """Snapshot dữ liệu chung cho frontend; QT01 và QT02 đọc từ cùng SQLite."""
    require_method(request, 'GET')
    booking_q = Booking.objects.select_related('customer', 'field', 'invoice').order_by('day', 'start_time')
    invoice_q = Invoice.objects.select_related('booking', 'customer').order_by('-created_at')
    recs = ReconciliationSession.objects.order_by('-day')[:60]
    exception_q = ReconciliationException.objects.select_related('session').order_by('-created_at')[:100]
    return JsonResponse({
        'today': timezone.localdate().isoformat(),
        'user': {
            'name': request.user.get_full_name() or request.user.username,
            'username': request.user.username,
            'role': role_of(request.user),
            'manager': role_of(request.user) == 'Manager',
        },
        'fields': [
            {'id': f.id, 'name': f.name, 'type': str(f.field_type), 'rate': int(f.hourly_rate),
             'active': f.is_active} for f in FootballField.objects.all().order_by('id')
        ],
        'products': [
            {'id': p.id, 'name': p.name, 'price': int(p.price), 'stock': p.stock,
             'unit': p.unit, 'tracksStock': p.tracks_stock, 'active': p.is_active}
            for p in Product.objects.all().order_by('id')
        ],
        'bookings': [booking_json(b) for b in booking_q[:1000]],
        'invoices': [invoice_json(i) | {
            'createdAt': i.created_at.isoformat(),
            'paidAt': i.paid_at.isoformat() if i.paid_at else None,
        } for i in invoice_q[:1000]],
        'reconciliations': [
            {'id': r.id, 'day': r.day.isoformat(), 'status': r.status,
             'countedCash': int(r.counted_cash) if r.counted_cash is not None else None,
             'ledgerCash': int(r.ledger_cash_snapshot) if r.ledger_cash_snapshot is not None else 0,
             'countedBank': int(r.bank_statement_total) if r.bank_statement_total is not None else None,
             'ledgerBank': int(r.ledger_bank_snapshot) if r.ledger_bank_snapshot is not None else 0,
             'notes': r.notes, 'approvedBy': r.approved_by.username if r.approved_by else None}
            for r in recs
        ],
        'exceptions': [
            {'id': x.id, 'day': x.session.day.isoformat(), 'description': x.description,
             'status': x.status, 'resolution': x.resolution}
            for x in exception_q
        ],
        'audits': [
            {'time': a.created_at.isoformat(), 'actor': a.actor.username,
             'event': a.event, 'detail': a.detail}
            for a in AuditLog.objects.select_related('actor').order_by('-created_at')[:100]
        ],
    })


@api
def product_create(request):
    """Tao hang hoa hoac dich vu moi vao danh muc san pham."""
    require_method(request, 'POST')
    d = data(request)
    name = str(d.get('name', '')).strip()
    unit = str(d.get('unit', '')).strip()
    tracks = d.get('tracksStock', True)
    if not name or len(name) > 100:
        raise ApiError('Ten san pham bat buoc, toi da 100 ky tu.')
    if not unit or len(unit) > 20:
        raise ApiError('Don vi tinh bat buoc, toi da 20 ky tu.')
    if not isinstance(tracks, bool):
        raise ApiError('Gia tri quan ly ton kho phai la true hoac false.')
    try:
        price = Decimal(str(d.get('price', '')))
        stock = int(d.get('stock', 0))
    except (ValueError, TypeError, ArithmeticError):
        raise ApiError('Gia ban hoac ton ban dau khong hop le.')
    if (not price.is_finite() or price < 0 or price > 1000000000
            or price != price.to_integral_value()):
        raise ApiError('Gia ban phai la so nguyen khong am, toi da 1 ty dong.')
    if stock < 0 or stock > 100000:
        raise ApiError('Ton ban dau phai tu 0 den 100.000.')
    if not tracks and stock != 0:
        raise ApiError('Dich vu khong theo doi ton phai co ton ban dau bang 0.')

    with transaction.atomic():
        if Product.objects.filter(name__iexact=name).exists():
            raise ApiError('Ten san pham da ton tai. Hay nhap them hang thay vi tao trung.', 409)
        p = Product.objects.create(
            name=name, price=price, unit=unit, stock=stock,
            tracks_stock=tracks, is_active=True,
        )
        if tracks and stock > 0:
            StockMovement.objects.create(
                product=p, delta=stock, stock_after=stock, actor=request.user,
            )
        log(request.user, 'product.create', f'Tao san pham {p.name}, gia {p.price}, ton {p.stock}')
    return JsonResponse({
        'ok': True,
        'product': {'id': p.id, 'name': p.name, 'unit': p.unit,
                    'price': int(p.price), 'stock': p.stock,
                    'tracksStock': p.tracks_stock, 'active': p.is_active},
    }, status=201)
