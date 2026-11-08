import hashlib
import json
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from operations.models import Invoice, Payment
from shared.api import ApiError
from .models import PendingItemResolution, ReconciliationException, ReconciliationSession

ZERO = Decimal('0')


def signed_payment_amount(payment):
    """Quy ước dòng tiền: thu dương, hoàn tiền âm."""
    value = abs(payment.amount)
    return -value if payment.kind == 'refund' else value


def _iso_datetime(value):
    if not value:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.isoformat()


def _local_date(value):
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value).date()


def _time_delta_minutes(payment_time, statement_time):
    if not payment_time or not statement_time:
        return None
    if timezone.is_naive(payment_time):
        payment_time = timezone.make_aware(payment_time, timezone.get_current_timezone())
    if timezone.is_naive(statement_time):
        statement_time = timezone.make_aware(statement_time, timezone.get_current_timezone())
    return round(abs((statement_time - payment_time).total_seconds()) / 60, 2)


def payments_for_day(day, method=None):
    qs = (
        Payment.objects.filter(business_day=day, status=Payment.Status.SUCCESS)
        .select_related('invoice', 'created_by', 'confirmed_by')
        .order_by('id')
    )
    if method:
        qs = qs.filter(method=method)
    return list(qs)


def ledger_totals(day):
    """Tổng hợp dòng tiền đã xác nhận; không đồng nhất với doanh thu kế toán."""
    cash = ZERO
    bank = ZERO
    cash_by_kind = {'deposit': ZERO, 'settlement': ZERO, 'refund': ZERO}
    bank_by_kind = {'deposit': ZERO, 'settlement': ZERO, 'refund': ZERO}

    for payment in payments_for_day(day):
        signed = signed_payment_amount(payment)
        if payment.method == 'cash':
            cash += signed
            cash_by_kind[payment.kind] = cash_by_kind.get(payment.kind, ZERO) + signed
        elif payment.method == 'bank':
            bank += signed
            bank_by_kind[payment.kind] = bank_by_kind.get(payment.kind, ZERO) + signed

    return {
        'cash': cash,
        'bank': bank,
        'cashByKind': cash_by_kind,
        'bankByKind': bank_by_kind,
    }


def payment_reference(payment):
    """Chỉ dùng mã giao dịch ngân hàng thực; không giả mạo bằng request_code nội bộ."""
    return (payment.bank_reference or '').strip()


def pending_invoices(day):
    """Hóa đơn đã phát sinh nghĩa vụ trong ngày nhưng còn phải thu tại mốc chốt."""
    candidates = (
        Invoice.objects.select_related('booking', 'customer')
        .prefetch_related('payments', 'lines')
        .filter(
            Q(booking__day=day, booking__status='completed')
            | Q(booking__isnull=True, created_at__date=day)
            | Q(payments__business_day=day)
        )
        .distinct()
        .order_by('id')
    )

    results = []
    for invoice in candidates:
        if invoice.booking_id and invoice.booking.day != day:
            # Tiền cọc lịch tương lai là dòng tiền trong ngày, không phải doanh thu dịch vụ ngày này.
            continue

        invoice_payments = list(invoice.payments.all())
        paid_at_cutoff = sum(
            (
                signed_payment_amount(payment)
                for payment in invoice_payments
                if payment.status == Payment.Status.SUCCESS and payment.business_day <= day
            ),
            ZERO,
        )
        current_collected = sum(
            (
                signed_payment_amount(payment)
                for payment in invoice_payments
                if payment.status == Payment.Status.SUCCESS
            ),
            ZERO,
        )
        due_at_cutoff = max(ZERO, invoice.total - paid_at_cutoff)
        current_due = max(ZERO, invoice.total - current_collected)
        paid_after_cutoff = any(
            payment.status == Payment.Status.SUCCESS and payment.business_day > day
            for payment in invoice_payments
        )

        if due_at_cutoff > 0:
            results.append({
                'invoice': invoice,
                'invoiceId': invoice.pk,
                'customer': invoice.customer_name or (
                    invoice.customer.name if invoice.customer_id else 'Khách lẻ'
                ),
                'amountDue': due_at_cutoff,
                'currentDue': current_due,
                'paidAfterCutoff': paid_after_cutoff,
            })
    return results


def bank_comparison(session):
    """So khớp từng phiếu chuyển khoản với sao kê bằng mã tham chiếu và số tiền.

    Thời điểm xác nhận của QT01 và thời điểm trên sao kê được lưu/hiển thị để
    nhân viên kiểm tra. Vì tài liệu chưa quy định ngưỡng lệch thời gian, hệ thống
    không tự kết luận sai lệch theo số phút.
    """
    payments = payments_for_day(session.day, method='bank')
    expected_by_ref = {}
    expected = []
    missing_reference = []

    for payment in payments:
        reference = payment_reference(payment)
        item = {
            'paymentId': payment.pk,
            'invoiceId': payment.invoice_id,
            'reference': reference,
            'amount': signed_payment_amount(payment),
            'kind': payment.kind,
            'requestCode': payment.request_code,
            'confirmedAt': _iso_datetime(payment.confirmed_at),
        }
        expected.append(item)
        if not reference:
            missing_reference.append(item)
            continue
        expected_by_ref.setdefault(reference.upper(), []).append(item)

    statement = getattr(session, 'bank_statement', None)
    actual_lines = list(statement.lines.all()) if statement else []
    actual_by_ref = {}
    date_mismatch = []

    for line in actual_lines:
        reference = line.transaction_ref.strip().upper()
        item = {
            'id': line.pk,
            'reference': line.transaction_ref,
            'amount': line.amount,
            'description': line.description,
            'transactionAt': _iso_datetime(line.transaction_at),
        }
        actual_by_ref.setdefault(reference, []).append(item)
        if line.transaction_at and _local_date(line.transaction_at) != session.day:
            date_mismatch.append({
                **item,
                'expectedDay': session.day.isoformat(),
                'actualDay': _local_date(line.transaction_at).isoformat(),
            })

    matched, missing, extra, mismatched, duplicate_expected = [], [], [], [], []
    for reference, items in expected_by_ref.items():
        if len(items) > 1:
            duplicate_expected.append(reference)

        actual_items = actual_by_ref.get(reference, [])
        if not actual_items:
            missing.extend(items)
            continue

        actual_line = actual_items[0]
        actual_model_line = next(
            line for line in actual_lines
            if line.transaction_ref.strip().upper() == reference
        )
        expected_amount = sum((item['amount'] for item in items), ZERO)
        if len(actual_items) > 1 or actual_line['amount'] != expected_amount:
            mismatched.append({
                'reference': items[0]['reference'],
                'expected': expected_amount,
                'actual': actual_line['amount'],
                'paymentIds': [item['paymentId'] for item in items],
                'description': actual_line['description'],
                'transactionAt': actual_line['transactionAt'],
            })
        else:
            payment_time = None
            if len(items) == 1:
                payment_time = next(
                    (p.confirmed_at for p in payments if p.pk == items[0]['paymentId']),
                    None,
                )
            matched.append({
                'reference': items[0]['reference'],
                'invoiceId': items[0]['invoiceId'],
                'paymentIds': [item['paymentId'] for item in items],
                'expected': expected_amount,
                'actual': actual_line['amount'],
                'paymentConfirmedAt': _iso_datetime(payment_time),
                'statementTransactionAt': actual_line['transactionAt'],
                'timeDeltaMinutes': _time_delta_minutes(
                    payment_time, actual_model_line.transaction_at
                ) if len(items) == 1 else None,
            })

    for reference, lines in actual_by_ref.items():
        if reference not in expected_by_ref:
            extra.extend(lines)

    return {
        'expected': expected,
        'actual': actual_lines,
        'matched': matched,
        'missing': missing,
        'missingReference': missing_reference,
        'extra': extra,
        'mismatched': mismatched,
        'dateMismatch': date_mismatch,
        'duplicateExpected': duplicate_expected,
        'expectedTotal': sum((item['amount'] for item in expected), ZERO),
        'actualTotal': sum((line.amount for line in actual_lines), ZERO),
        'imported': statement is not None,
        'source': statement.source_name if statement else '',
        'importedAt': statement.imported_at.isoformat() if statement else None,
    }


def reconciliation_summary(session):
    totals = ledger_totals(session.day)
    cash_expected = None
    cash_difference = None
    if session.opening_cash is not None and session.counted_cash is not None:
        cash_expected = session.opening_cash + totals['cash'] - session.cash_transfer_out
        cash_difference = session.counted_cash - cash_expected

    bank = bank_comparison(session)
    bank_difference = None if not bank['imported'] else bank['actualTotal'] - bank['expectedTotal']
    pending = pending_invoices(session.day)
    resolutions = {
        item.source_invoice_id: item
        for item in session.pending_resolutions.all()
    }

    return {
        'ledgerCash': totals['cash'],
        'ledgerBank': totals['bank'],
        'cashByKind': totals['cashByKind'],
        'bankByKind': totals['bankByKind'],
        'cashExpected': cash_expected,
        'cashDifference': cash_difference,
        'countedCash': session.counted_cash,
        'openingCash': session.opening_cash,
        'cashTransferOut': session.cash_transfer_out,
        'bankDifference': bank_difference,
        'bank': bank,
        'pendingInvoices': [
            {
                'invoiceId': item['invoiceId'],
                'customer': item['customer'],
                'amountDue': item['amountDue'],
                'currentDue': item['currentDue'],
                'paidAfterCutoff': item['paidAfterCutoff'],
                'resolution': pending_resolution_json(resolutions.get(item['invoiceId'])),
            }
            for item in pending
        ],
        'pendingCount': len(pending),
    }


def pending_resolution_json(resolution):
    if not resolution:
        return None
    return {
        'disposition': resolution.disposition,
        'note': resolution.note,
        'amountDueAtCutoff': int(resolution.amount_due_at_cutoff),
        'recordedAt': resolution.created_at.isoformat(),
        'recordedBy': resolution.recorded_by.username,
    }


def build_fingerprint(session):
    """Fingerprint toàn bộ dữ liệu QT01 liên quan, gồm cả khoản thu sau ngày chốt."""
    relevant_invoices = (
        Invoice.objects.filter(
            Q(booking__day=session.day)
            | Q(created_at__date=session.day)
            | Q(payments__business_day=session.day)
        )
        .distinct()
        .prefetch_related('lines')
        .select_related('booking')
        .order_by('id')
    )
    invoice_rows = []
    invoice_ids = []

    for invoice in relevant_invoices:
        invoice_ids.append(invoice.pk)
        invoice_rows.append({
            'id': invoice.pk,
            'status': invoice.status,
            'total': str(invoice.total),
            'bookingId': invoice.booking_id,
            'bookingDay': invoice.booking.day.isoformat() if invoice.booking_id else None,
            'bookingStatus': invoice.booking.status if invoice.booking_id else None,
            'lines': [
                [line.pk, line.kind, line.description, line.quantity, str(line.unit_price)]
                for line in invoice.lines.all().order_by('id')
            ],
        })

    related_payments = Payment.objects.filter(invoice_id__in=invoice_ids).select_related(
        'created_by', 'confirmed_by'
    ).order_by('id')
    payment_rows = [
        {
            'id': payment.pk,
            'invoice': payment.invoice_id,
            'kind': payment.kind,
            'method': payment.method,
            'amount': str(payment.amount),
            'status': payment.status,
            'requestCode': payment.request_code,
            'bankReference': payment.bank_reference or '',
            'businessDay': payment.business_day.isoformat(),
            'confirmedAt': _iso_datetime(payment.confirmed_at),
            'confirmedBy': payment.confirmed_by_id,
        }
        for payment in related_payments
    ]

    statement = getattr(session, 'bank_statement', None)
    statement_lines = []
    if statement:
        statement_lines = [
            [
                line.transaction_ref,
                str(line.amount),
                line.description,
                _iso_datetime(line.transaction_at),
            ]
            for line in statement.lines.order_by('transaction_ref', 'id')
        ]

    pending = [
        [
            item.source_invoice_id,
            item.disposition,
            item.note,
            str(item.amount_due_at_cutoff),
            item.recorded_by_id,
        ]
        for item in session.pending_resolutions.order_by('source_invoice_id')
    ]

    source = {
        'day': session.day.isoformat(),
        'payments': payment_rows,
        'invoices': invoice_rows,
        'openingCash': str(session.opening_cash) if session.opening_cash is not None else None,
        'cashTransferOut': str(session.cash_transfer_out),
        'countedCash': str(session.counted_cash) if session.counted_cash is not None else None,
        'bankStatement': {
            'source': statement.source_name if statement else None,
            'lines': statement_lines,
        },
        'pending': pending,
    }
    raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def exception_specs(session):
    summary = reconciliation_summary(session)
    specs = []

    cash_diff = summary['cashDifference']
    if summary['cashExpected'] is not None and summary['cashExpected'] < 0:
        specs.append({
            'code': 'cash:negative-expected',
            'category': ReconciliationException.Category.OTHER,
            'description': 'Quỹ cuối kỳ dự kiến đang âm; cần kiểm tra quỹ đầu ca và các khoản chi ra khỏi két.',
            'amount_difference': summary['cashExpected'],
        })

    if cash_diff is not None and cash_diff != 0:
        category = (
            ReconciliationException.Category.CASH_SHORTAGE if cash_diff < 0
            else ReconciliationException.Category.CASH_OVERAGE
        )
        specs.append({
            'code': 'cash:variance',
            'category': category,
            'description': (
                f"Quỹ tiền mặt {'thiếu' if cash_diff < 0 else 'thừa'} "
                f"{abs(cash_diff):,.0f} VNĐ so với số dự kiến."
            ),
            'amount_difference': cash_diff,
        })

    bank = summary['bank']
    for item in bank['missingReference']:
        specs.append({
            'code': f"bank:missing-reference:{item['paymentId']}",
            'category': ReconciliationException.Category.BANK_REFERENCE_MISSING,
            'description': (
                f"Phiếu thanh toán chuyển khoản #{item['paymentId']} (hóa đơn "
                f"#{item['invoiceId']}) chưa có mã tham chiếu ngân hàng."
            ),
            'amount_difference': item['amount'],
        })

    if bank['imported']:
        for item in bank['missing']:
            specs.append({
                'code': f"bank:missing:{item['reference'].upper()}",
                'category': ReconciliationException.Category.BANK_MISSING,
                'description': f"Giao dịch {item['reference']} có trong hệ thống nhưng không thấy trên sao kê.",
                'amount_difference': item['amount'],
            })
        for item in bank['extra']:
            specs.append({
                'code': f"bank:extra:{item['reference'].upper()}",
                'category': ReconciliationException.Category.BANK_EXTRA,
                'description': f"Giao dịch {item['reference']} có trên sao kê nhưng không tìm thấy trong hệ thống.",
                'amount_difference': item['amount'],
            })
        for item in bank['mismatched']:
            specs.append({
                'code': f"bank:mismatch:{item['reference'].upper()}",
                'category': ReconciliationException.Category.BANK_MISMATCH,
                'description': (
                    f"Giao dịch {item['reference']} sai số tiền: hệ thống "
                    f"{item['expected']:,.0f}, sao kê {item['actual']:,.0f} VNĐ."
                ),
                'amount_difference': item['actual'] - item['expected'],
            })
        for item in bank['dateMismatch']:
            specs.append({
                'code': f"bank:date-mismatch:{item['id']}",
                'category': ReconciliationException.Category.BANK_DATE_MISMATCH,
                'description': (
                    f"Giao dịch {item['reference']} có thời điểm trên sao kê thuộc ngày "
                    f"{item['actualDay']}, không thuộc kỳ đối soát {item['expectedDay']}."
                ),
                'amount_difference': item['amount'],
            })
        for reference in bank['duplicateExpected']:
            specs.append({
                'code': f'bank:duplicate:{reference}',
                'category': ReconciliationException.Category.BANK_MISMATCH,
                'description': f"Mã tham chiếu {reference} bị trùng trong sổ thanh toán.",
                'amount_difference': None,
            })

    return specs


def detect_exceptions(session, actor):
    """Tạo/cập nhật ngoại lệ theo dữ liệu hiện tại; đóng ngoại lệ khi chênh lệch đã hết."""
    current_specs = {item['code']: item for item in exception_specs(session)}
    active = session.exceptions.exclude(status=ReconciliationException.Status.RESOLVED)

    for case in active:
        if case.code not in current_specs:
            case.status = ReconciliationException.Status.RESOLVED
            case.resolution = 'Đối chiếu lại: chênh lệch không còn tồn tại.'
            case.resolved_by = actor
            case.resolved_at = timezone.now()
            case.save(update_fields=[
                'status', 'resolution', 'resolved_by', 'resolved_at', 'updated_at'
            ])

    created_or_updated = []
    for code, spec in current_specs.items():
        case, created = ReconciliationException.objects.get_or_create(
            session=session,
            code=code,
            defaults={
                **spec,
                'created_by': actor,
                'status': ReconciliationException.Status.OPEN,
            },
        )
        if not created:
            changed = (
                case.category != spec['category']
                or case.description != spec['description']
                or case.amount_difference != spec['amount_difference']
            )
            if changed or case.status == ReconciliationException.Status.RESOLVED:
                case.category = spec['category']
                case.description = spec['description']
                case.amount_difference = spec['amount_difference']
                case.status = ReconciliationException.Status.OPEN
                case.manager_feedback = 'Số liệu thay đổi hoặc chênh lệch phát sinh lại; cần giải trình và duyệt lại.'
                case.reviewed_by = None
                case.reviewed_at = None
                case.resolved_by = None
                case.resolved_at = None
                case.resolution = ''
                case.save()
        created_or_updated.append(case)

    return created_or_updated


def all_exceptions_accepted(session):
    return not session.exceptions.exclude(
        status__in=[
            ReconciliationException.Status.APPROVED,
            ReconciliationException.Status.RESOLVED,
        ]
    ).exists()


def unresolved_pending(session):
    pending = {item['invoiceId']: item for item in pending_invoices(session.day)}
    resolutions = {
        item.source_invoice_id: item
        for item in session.pending_resolutions.all()
    }
    unresolved = set()

    for invoice_id, item in pending.items():
        resolution = resolutions.get(invoice_id)
        if resolution is None or resolution.amount_due_at_cutoff != item['amountDue']:
            unresolved.add(invoice_id)
            continue

        if item['paidAfterCutoff'] and item['currentDue'] == 0:
            if resolution.disposition != PendingItemResolution.Disposition.SETTLED_LATER:
                unresolved.add(invoice_id)
        elif resolution.disposition == PendingItemResolution.Disposition.SETTLED_LATER:
            # Không cho ghi "đã tất toán sau ngày chốt" nếu hiện vẫn còn nợ.
            unresolved.add(invoice_id)

    return unresolved


def validate_pending_disposition(session):
    unresolved = unresolved_pending(session)
    if unresolved:
        raise ApiError(
            'Còn hóa đơn treo chưa có phương án chuyển tiếp hợp lệ: '
            + ', '.join(str(item) for item in sorted(unresolved)),
            409,
        )


def validate_recon_ready(session):
    summary = reconciliation_summary(session)
    if session.opening_cash is None or session.counted_cash is None:
        raise ApiError('Chưa nhập quỹ đầu ca và số tiền mặt thực kiểm.', 409)
    if not summary['bank']['imported']:
        raise ApiError('Chưa nhập sao kê ngân hàng (có thể nhập danh sách rỗng nếu không phát sinh).', 409)
    validate_pending_disposition(session)

    current_specs = {item['code']: item for item in exception_specs(session)}
    cases = {case.code: case for case in session.exceptions.all()}

    for code, spec in current_specs.items():
        case = cases.get(code)
        if (
            case is None
            or case.status != ReconciliationException.Status.APPROVED
            or case.category != spec['category']
            or case.description != spec['description']
            or case.amount_difference != spec['amount_difference']
        ):
            raise ApiError(
                'Có chênh lệch mới hoặc chưa được Quản lý chấp nhận. '
                'Hãy chạy phát hiện ngoại lệ, giải trình và chờ Quản lý xử lý.',
                409,
            )

    for case in session.exceptions.exclude(status=ReconciliationException.Status.RESOLVED):
        if case.code not in current_specs:
            raise ApiError(
                'Có ngoại lệ đã hết chênh lệch nhưng chưa cập nhật trạng thái. '
                'Hãy chạy lại bước phát hiện ngoại lệ.',
                409,
            )

    if not all_exceptions_accepted(session):
        raise ApiError('Còn ngoại lệ chưa được giải trình và Quản lý chấp nhận.', 409)
    return summary


def report_payload(session):
    summary = reconciliation_summary(session)
    bank = summary['bank']
    payment_rows = []

    for payment in payments_for_day(session.day):
        payment_rows.append({
            'paymentId': payment.pk,
            'invoiceId': payment.invoice_id,
            'kind': payment.kind,
            'method': payment.method,
            'amount': int(signed_payment_amount(payment)),
            'requestCode': payment.request_code,
            'bankReference': payment.bank_reference or '',
            'businessDay': payment.business_day.isoformat(),
            'status': payment.status,
            'confirmedAt': _iso_datetime(payment.confirmed_at),
            'createdBy': payment.created_by.username if payment.created_by_id else None,
            'confirmedBy': payment.confirmed_by.username if payment.confirmed_by_id else None,
        })

    return {
        'day': session.day.isoformat(),
        'status': session.status,
        'sourceFingerprint': session.source_fingerprint,
        'createdAt': session.created_at.isoformat(),
        'submittedAt': session.submitted_at.isoformat() if session.submitted_at else None,
        'approvedAt': session.approved_at.isoformat() if session.approved_at else None,
        'lockedAt': session.locked_at.isoformat() if session.locked_at else None,
        'summary': {
            'ledgerCash': int(summary['ledgerCash']),
            'cashByKind': {key: int(value) for key, value in summary['cashByKind'].items()},
            'openingCash': int(session.opening_cash or 0),
            'cashTransferOut': int(session.cash_transfer_out),
            'cashExpected': int(summary['cashExpected'] or 0),
            'countedCash': int(session.counted_cash or 0),
            'cashDifference': int(summary['cashDifference'] or 0),
            'ledgerBank': int(summary['ledgerBank']),
            'bankByKind': {key: int(value) for key, value in summary['bankByKind'].items()},
            'statementBank': int(bank['actualTotal']) if bank['imported'] else None,
            'bankDifference': int(summary['bankDifference']) if summary['bankDifference'] is not None else None,
        },
        'payments': payment_rows,
        'bank': {
            'source': bank['source'],
            'expected': [
                {
                    'paymentId': item['paymentId'],
                    'invoiceId': item['invoiceId'],
                    'reference': item['reference'],
                    'amount': int(item['amount']),
                    'kind': item['kind'],
                    'requestCode': item['requestCode'],
                    'confirmedAt': item['confirmedAt'],
                }
                for item in bank['expected']
            ],
            'matched': [
                {
                    **item,
                    'expected': int(item['expected']),
                    'actual': int(item['actual']),
                }
                for item in bank['matched']
            ],
            'missing': [
                {**item, 'amount': int(item['amount'])}
                for item in bank['missing']
            ],
            'missingReference': [
                {**item, 'amount': int(item['amount'])}
                for item in bank['missingReference']
            ],
            'extra': [
                {**item, 'amount': int(item['amount'])}
                for item in bank['extra']
            ],
            'mismatched': [
                {**item, 'expected': int(item['expected']), 'actual': int(item['actual'])}
                for item in bank['mismatched']
            ],
            'dateMismatch': [
                {**item, 'amount': int(item['amount'])}
                for item in bank['dateMismatch']
            ],
        },
        'pendingInvoices': [
            {
                **item,
                'amountDue': int(item['amountDue']),
                'currentDue': int(item['currentDue']),
            }
            for item in summary['pendingInvoices']
        ],
        'exceptions': [
            {
                'id': case.pk,
                'code': case.code,
                'category': case.category,
                'description': case.description,
                'amountDifference': int(case.amount_difference) if case.amount_difference is not None else None,
                'status': case.status,
                'reason': case.reason,
                'evidence': case.evidence,
                'proposedAction': case.proposed_action,
                'managerFeedback': case.manager_feedback,
                'resolution': case.resolution,
            }
            for case in session.exceptions.order_by('id')
        ],
        'notes': session.notes,
    }


def assert_draft(session):
    if session.status != ReconciliationSession.Status.DRAFT:
        raise ApiError('Kỳ đối soát không còn ở trạng thái nháp.', 409)


def assert_not_future(day):
    if day > timezone.localdate():
        raise ApiError('Không thể mở kỳ đối soát cho ngày trong tương lai.', 400)
