"""Quy tắc hủy sân tính tại server, không cần AI."""
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from operations.models import Booking, Invoice, Payment, Reconciliation
from process_2.models import ReconciliationSession

REASON_TYPES = ('personal', 'weather', 'other')

def evaluate_cancellation(booking, invoice, reason_type='personal', now=None):
    if reason_type not in REASON_TYPES:
        raise ValueError('Loại lý do hủy không hợp lệ.')

    now = timezone.localtime(now or timezone.now())
    start = timezone.make_aware(
        datetime.combine(booking.day, booking.start_time),
        timezone.get_current_timezone()
    )
    minutes_to_start = int((start - now).total_seconds() // 60)

    deposit = sum(
        (abs(p.amount) for p in invoice.payments.filter(
            kind='deposit',
            status=Payment.Status.SUCCESS
        )),
        Decimal('0')
    )

    pending = invoice.payments.filter(
        status=Payment.Status.PENDING
    ).exists()

    refund_exists = invoice.payments.filter(
        kind='refund',
        status=Payment.Status.SUCCESS
    ).exists()

    services_exist = invoice.lines.exclude(
        kind='rental'
    ).exists()

    locked = (
        Reconciliation.objects.filter(
            day=booking.day, status='locked'
        ).exists()
        or ReconciliationSession.objects.filter(
            day=booking.day, status='locked'
        ).exists()
    )

    blockers = []

    if booking.status != Booking.Status.BOOKED:
        blockers.append({
            Booking.Status.USING:
                'Khách đã nhận sân: sử dụng quy trình Trả sân.',
            Booking.Status.COMPLETED:
                'Khách đã trả sân, không được hủy lần nữa.',
            Booking.Status.CANCELLED:
                'Lịch đã được hủy trước đó.'
        }.get(
            booking.status,
            'Trạng thái lịch không hợp lệ.'
        ))

    if booking.received_at:
        blockers.append(
            'Đã ghi nhận thời điểm nhận sân.'
        )

    if invoice.status != Invoice.Status.DRAFT:
        blockers.append(
            'Hóa đơn không ở trạng thái Nháp.'
        )

    if locked:
        blockers.append(
            'Ngày sử dụng đã khóa sổ.'
        )

    if minutes_to_start <= 0:
        blockers.append(
            'Đã đến hoặc quá giờ đặt: '
            'chuyển quản lý xử lý ngoại lệ.'
        )

    if services_exist:
        blockers.append(
            'Hóa đơn đã có hàng hóa/dịch vụ, cần xử lý riêng.'
        )

    if pending:
        blockers.append(
            'Có giao dịch đang chờ xác minh.'
        )

    if refund_exists:
        blockers.append(
            'Đã có giao dịch hoàn tiền, cần đối chiếu.'
        )

    if minutes_to_start >= 1440:
        clause, percent = '1.1', 100
    elif minutes_to_start >= 120:
        clause, percent = '1.2', 50
    else:
        clause, percent = '1.3', 0

    proposal_percent = (
        None if reason_type == 'weather' else percent
    )

    proposal_money = (
        None if proposal_percent is None
        else int(
            (deposit * Decimal(proposal_percent)
             / Decimal(100)).quantize(Decimal('1'))
        )
    )

    if blockers:
        decision = 'blocked'
    elif deposit > 0 or reason_type == 'weather':
        decision = 'review'
    else:
        decision = 'allowed'

    return {
        'decision': decision,
        'canCancel': not blockers,
        'requiresManagerReview': bool(
            deposit > 0 or reason_type == 'weather'
        ),
        'policyClause': (
            '2' if reason_type == 'weather' else clause
        ),
        'standardTimeClause': clause,
        'minutesBeforeStart': minutes_to_start,
        'depositReceivedVnd': int(deposit),
        'suggestedRefundPercent': proposal_percent,
        'suggestedRefundVnd': proposal_money,
        'weatherPotentialRefundVnd': (
            int(deposit) if reason_type == 'weather'
            else None
        ),
        'blockers': blockers,
        'reasonType': reason_type,
        'evaluatedAt': now.isoformat(timespec='seconds'),
        'notice': (
            'Không được hủy lịch trực tiếp.'
            if blockers else
            'Chỉ hủy lịch, không tự hoàn tiền; '
            'chủ sân xử lý cọc.'
            if deposit > 0 else
            'Có thể hủy lịch, không có cọc cần hoàn.'
        ),
        'weatherNotice': (
            'Thời tiết chưa được xác minh: '
            'không tự kết luận được hoàn 100%.'
            if reason_type == 'weather' else None
        )
    }
