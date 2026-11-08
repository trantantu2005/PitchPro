import csv
import io
import hashlib
from pathlib import Path
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from operations.models import Invoice, Reconciliation as LegacyReconciliation
from shared.api import ApiError, api, amount, as_date, data, ensure_unlocked, log, require_method, staff_manager, require_role
from .models import (
    BankStatement, BankStatementLine, PendingItemResolution,
    ReconciliationException, ReconciliationExceptionHistory,
    ReconciliationAIAnalysis, ReconciliationEvidenceDocument,
    ReconciliationReminder, ReconciliationSession,
)
from .ai_service import (
    AIServiceError, ai_provider, ai_status, context_fingerprint, generate_qt02_suggestion,
)
from .services import (
    all_exceptions_accepted, assert_draft, assert_not_future, bank_comparison,
    build_fingerprint, detect_exceptions, ledger_totals, pending_invoices,
    reconciliation_summary, report_payload, unresolved_pending, validate_recon_ready,
)


def manager_required(request):
    staff_manager(request.user)


def employee_required(request):
    """Chi nhom Staff duoc xu ly cac buoc nhan vien QT02."""
    require_role(request.user, 'Staff')


def _next_exception_revision(case):
    current = case.history_entries.aggregate(value=Max('revision_no'))['value'] or 0
    return current + 1


def _ai_analysis_json(analysis):
    if not analysis:
        return None
    return {
        'id': analysis.id,
        'type': analysis.analysis_type,
        'provider': analysis.provider,
        'model': analysis.model_name,
        'result': analysis.result,
        'createdAt': analysis.created_at.isoformat(),
        'sourceFingerprint': analysis.source_fingerprint,
    }


def _extract_evidence_text(uploaded_file, raw):
    name = uploaded_file.name.replace('\\', '/').split('/')[-1]
    extension = Path(name).suffix.lower()
    if extension not in {'.pdf', '.txt', '.csv'}:
        raise ApiError('Chỉ hỗ trợ chứng từ PDF có văn bản, TXT hoặc CSV.')
    if extension == '.pdf':
        if not raw.startswith(b'%PDF'):
            raise ApiError('Tệp không có định dạng PDF hợp lệ.')
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw), strict=False)
            if reader.is_encrypted:
                raise ApiError('PDF đang được mã hóa; hãy tải bản PDF không đặt mật khẩu.')
            if len(reader.pages) > 20:
                raise ApiError('PDF vượt giới hạn 20 trang cho một lần đọc.')
            text = '\n'.join((page.extract_text() or '') for page in reader.pages)
        except ApiError:
            raise
        except Exception:
            raise ApiError('Không đọc được nội dung PDF. Hãy kiểm tra tệp hoặc chuyển sang PDF có văn bản.')
        if not text.strip():
            raise ApiError(
                'PDF có thể là bản scan/ảnh; bản demo chưa tích hợp OCR. Hãy dán nội dung chứng từ dạng văn bản.')
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = raw.decode('cp1258')
            except UnicodeDecodeError:
                raise ApiError('Không đọc được tệp văn bản. Hãy lưu TXT/CSV bằng mã hóa UTF-8.')
    return name[:255], extension, text[:20000]


def session_for_day(day):
    session = ReconciliationSession.objects.filter(day=day).first()
    if not session:
        raise ApiError(f'Chưa mở kỳ đối soát ngày {day}.', 404)
    return session


def exception_for_session(session, exception_id):
    case = ReconciliationException.objects.filter(pk=exception_id, session=session).first()
    if not case:
        raise ApiError('Không tìm thấy ngoại lệ thuộc kỳ đối soát này.', 404)
    return case


def exception_json(case):
    latest_ai = case.ai_analyses.order_by('-created_at').first()
    return {
        'id': case.id,
        'code': case.code,
        'category': case.category,
        'categoryLabel': case.get_category_display(),
        'description': case.description,
        'amountDifference': int(case.amount_difference) if case.amount_difference is not None else None,
        'status': case.status,
        'statusLabel': case.get_status_display(),
        'reason': case.reason,
        'evidence': case.evidence,
        'proposedAction': case.proposed_action,
        'managerFeedback': case.manager_feedback,
        'resolution': case.resolution,
        'createdAt': case.created_at.isoformat(),
        'submittedAt': case.submitted_at.isoformat() if case.submitted_at else None,
        'reviewedAt': case.reviewed_at.isoformat() if case.reviewed_at else None,
        'resolvedAt': case.resolved_at.isoformat() if case.resolved_at else None,
        'history': [
            {
                'revisionNo': item.revision_no,
                'action': item.get_action_display(),
                'status': item.status,
                'reason': item.reason,
                'evidence': item.evidence,
                'proposedAction': item.proposed_action,
                'managerFeedback': item.manager_feedback,
                'actor': item.actor.username,
                'createdAt': item.created_at.isoformat(),
            }
            for item in case.history_entries.select_related('actor').all()
        ],
        'evidenceDocuments': [
            {
                'id': item.id,
                'originalName': item.original_name,
                'sizeBytes': item.size_bytes,
                'uploadedBy': item.uploaded_by.username,
                'uploadedAt': item.uploaded_at.isoformat(),
            }
            for item in case.evidence_documents.select_related('uploaded_by').all()
        ],
        'aiAnalysis': _ai_analysis_json(latest_ai),
    }


def reconciliation_json(session):
    summary = reconciliation_summary(session)
    bank = summary['bank']
    exceptions = [exception_json(x) for x in session.exceptions.order_by('id')]
    pending = summary['pendingInvoices']
    return {
        'ai': ai_status(),
        'id': session.id,
        'day': session.day.isoformat(),
        'status': session.status,
        'createdAt': session.created_at.isoformat(),
        'submittedAt': session.submitted_at.isoformat() if session.submitted_at else None,
        'approvedAt': session.approved_at.isoformat() if session.approved_at else None,
        'lockedAt': session.locked_at.isoformat() if session.locked_at else None,
        'createdBy': session.created_by.username,
        'approvedBy': session.approved_by.username if session.approved_by else None,
        'lockedBy': session.locked_by.username if session.locked_by else None,
        'notes': session.notes,
        'openingCash': int(session.opening_cash) if session.opening_cash is not None else None,
        'cashTransferOut': int(session.cash_transfer_out),
        'countedCash': int(session.counted_cash) if session.counted_cash is not None else None,
        'ledgerCash': int(summary['ledgerCash']),
        'cashByKind': {key: int(value) for key, value in summary['cashByKind'].items()},
        'cashExpected': int(summary['cashExpected']) if summary['cashExpected'] is not None else None,
        'cashDifference': int(summary['cashDifference']) if summary['cashDifference'] is not None else None,
        'ledgerBank': int(summary['ledgerBank']),
        'bankByKind': {key: int(value) for key, value in summary['bankByKind'].items()},
        'statementBank': int(bank['actualTotal']) if bank['imported'] else None,
        'bankDifference': int(summary['bankDifference']) if summary['bankDifference'] is not None else None,
        'bank': {
            'imported': bank['imported'],
            'source': bank['source'],
            'importedAt': bank['importedAt'],
            'expectedTotal': int(bank['expectedTotal']),
            'actualTotal': int(bank['actualTotal']),
            'expected': [
                {'paymentId': x['paymentId'], 'invoiceId': x['invoiceId'],
                 'reference': x['reference'], 'amount': int(x['amount']), 'kind': x['kind'],
                 'requestCode': x['requestCode'], 'confirmedAt': x['confirmedAt']}
                for x in bank['expected']
            ],
            'matched': bank['matched'],
            'missing': bank['missing'],
            'missingReference': bank['missingReference'],
            'extra': bank['extra'],
            'mismatched': bank['mismatched'],
            'dateMismatch': bank['dateMismatch'],
            'duplicateExpected': bank['duplicateExpected'],
            'actual': [
                {'id': x.id, 'reference': x.transaction_ref, 'amount': int(x.amount),
                 'description': x.description,
                 'transactionAt': x.transaction_at.isoformat() if x.transaction_at else None}
                for x in bank['actual']
            ],
        },
        'pendingInvoices': pending,
        'unresolvedPendingIds': sorted(unresolved_pending(session)),
        'exceptions': exceptions,
        'reportSnapshot': session.report_snapshot if session.status == 'locked' else None,
        'canEdit': session.status == ReconciliationSession.Status.DRAFT,
    }


@api
def reconciliation(request):
    """QT02: GET xem kỳ; POST mở kỳ đối soát. Dữ liệu thu chỉ đọc từ QT01."""
    if request.method == 'GET':
        require_method(request, 'GET')
        day = as_date(request.GET.get('date', timezone.localdate().isoformat()))
        session = ReconciliationSession.objects.filter(day=day).first()
        if not session:
            totals = ledger_totals(day)
            return JsonResponse({
                'day': day.isoformat(),
                'session': None,
                'ai': ai_status(),
                'status': None,
                'ledgerCash': int(totals['cash']),
                'cashByKind': {key: int(value) for key, value in totals['cashByKind'].items()},
                'ledgerBank': int(totals['bank']),
                'bankByKind': {key: int(value) for key, value in totals['bankByKind'].items()},
                'canOpen': (
                        day <= timezone.localdate()
                        and not LegacyReconciliation.objects.filter(day=day, status='locked').exists()
                ),
                'pendingInvoices': [],
                'exceptions': [],
            })
        payload = reconciliation_json(session)
        payload['session'] = payload.copy()
        return JsonResponse(payload)

    require_method(request, 'POST')
    employee_required(request)
    body = data(request)
    day = as_date(body.get('date'))
    assert_not_future(day)
    ensure_unlocked(day)

    with transaction.atomic():
        session, created = ReconciliationSession.objects.get_or_create(
            day=day,
            defaults={'created_by': request.user},
        )
        if not created:
            if session.status == ReconciliationSession.Status.LOCKED:
                raise ApiError('Kỳ này đã khóa sổ.', 409)
            raise ApiError('Kỳ đối soát đã được mở trước đó.', 409)
        log(request.user, 'qt02.open', f'Mở kỳ đối soát doanh thu ngày {day.isoformat()}')
    return JsonResponse({'id': session.id, 'day': day.isoformat(), 'status': session.status}, status=201)


@api
def cash_count(request, day):
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    body = data(request)
    opening = amount(body.get('openingCash'), allow_zero=True)
    transfer = amount(body.get('cashTransferOut', 0), allow_zero=True)
    counted = amount(body.get('countedCash'), allow_zero=True)
    note = str(body.get('notes', '')).strip()
    if len(note) < 5:
        raise ApiError('Cần ghi căn cứ kiểm đếm quỹ tối thiểu 5 ký tự.')
    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        session.opening_cash = opening
        session.cash_transfer_out = transfer
        session.counted_cash = counted
        session.notes = note[:4000]
        session.save()
        detect_exceptions(session, request.user)
        # Mọi thay đổi nguồn phải làm mới fingerprint và buộc duyệt lại ngoại lệ cũ.
        for case in session.exceptions.filter(status=ReconciliationException.Status.APPROVED):
            case.status = ReconciliationException.Status.OPEN
            case.manager_feedback = 'Số liệu quỹ thay đổi; cần giải trình và duyệt lại.'
            case.save(update_fields=['status', 'manager_feedback', 'updated_at'])
        log(request.user, 'qt02.cash_count',
            f'Kiểm quỹ ngày {business_day}: đầu {opening}, thu/hoàn ròng {ledger_totals(business_day)["cash"]}, nộp quỹ {transfer}, thực đếm {counted}')
    return JsonResponse(reconciliation_json(session))


@api
def bank_statement_import(request, day):
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    body = data(request)
    source = str(body.get('source', '')).strip()
    rows = body.get('rows')
    if len(source) < 3:
        raise ApiError('Tên nguồn sao kê tối thiểu 3 ký tự.')
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ApiError('Sao kê phải là danh sách tối đa 2.000 giao dịch.')
    parsed = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ApiError(f'Dòng {index}: dữ liệu giao dịch không hợp lệ.')
        reference = str(row.get('reference', '')).strip()
        if len(reference) < 3 or len(reference) > 120:
            raise ApiError(f'Dòng {index}: mã giao dịch cần từ 3 đến 120 ký tự.')
        normalized = reference.upper()
        if normalized in seen:
            raise ApiError(f'Dòng {index}: mã giao dịch bị trùng ({reference}).')
        seen.add(normalized)
        value = amount(row.get('amount'), allow_zero=False, allow_negative=True)
        description = str(row.get('description', '')).strip()[:250]
        raw_transaction_at = row.get('transactionAt') or row.get('transaction_at')
        transaction_at = None
        if raw_transaction_at:
            transaction_at = parse_datetime(str(raw_transaction_at).strip())
            if transaction_at is None:
                raise ApiError(
                    f'Dòng {index}: thời điểm giao dịch không hợp lệ; dùng ISO 8601, '
                    'ví dụ 2026-10-31T18:30:00+07:00.'
                )
            if timezone.is_naive(transaction_at):
                transaction_at = timezone.make_aware(
                    transaction_at, timezone.get_current_timezone()
                )
        parsed.append({
            'reference': reference,
            'amount': value,
            'description': description,
            'transaction_at': transaction_at,
        })

    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        statement, _ = BankStatement.objects.get_or_create(
            session=session,
            defaults={'source_name': source, 'imported_by': request.user},
        )
        statement.source_name = source[:180]
        statement.imported_by = request.user
        statement.imported_at = timezone.now()
        statement.row_count = len(parsed)
        statement.total_amount = sum((x['amount'] for x in parsed), Decimal('0'))
        statement.save()
        statement.lines.all().delete()
        BankStatementLine.objects.bulk_create([
            BankStatementLine(
                statement=statement,
                transaction_ref=x['reference'],
                amount=x['amount'],
                description=x['description'],
                transaction_at=x['transaction_at'],
            )
            for x in parsed
        ])
        detect_exceptions(session, request.user)
        for case in session.exceptions.filter(
                status__in=[
                    ReconciliationException.Status.APPROVED,
                    ReconciliationException.Status.REVIEW_PENDING,
                    ReconciliationException.Status.REJECTED,
                ]
        ):
            case.status = ReconciliationException.Status.OPEN
            case.manager_feedback = 'Sao kê được nhập lại; cần kiểm tra và duyệt lại theo dữ liệu mới.'
            case.save(update_fields=['status', 'manager_feedback', 'updated_at'])
        log(request.user, 'qt02.bank_import', f'Nhập {len(parsed)} dòng sao kê ngày {business_day} từ {source}')
    return JsonResponse(reconciliation_json(session))


@api
def detect(request, day):
    require_method(request, 'POST')
    employee_required(request)
    session = session_for_day(as_date(day))
    assert_draft(session)
    with transaction.atomic():
        cases = detect_exceptions(session, request.user)
        summary = reconciliation_summary(session)
    log(request.user, 'qt02.detect', f'Kiểm tra chênh lệch ngày {session.day}: {len(cases)} ngoại lệ đang có')
    return JsonResponse({
        'createdOrUpdated': len(cases),
        'summary': {
            'cashDifference': int(summary['cashDifference']) if summary['cashDifference'] is not None else None,
            'bankDifference': int(summary['bankDifference']) if summary['bankDifference'] is not None else None,
        },
        'reconciliation': reconciliation_json(session),
    })


@api
def pending_resolution(request, day, invoice_id):
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    body = data(request)
    disposition = body.get('disposition')
    note = str(body.get('note', '')).strip()
    if disposition not in [x[0] for x in PendingItemResolution.Disposition.choices]:
        raise ApiError('Phương án khoản treo không hợp lệ.')
    if len(note) < 10:
        raise ApiError('Ghi rõ lý do và phương án tối thiểu 10 ký tự.')
    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        item = next((x for x in pending_invoices(business_day) if x['invoiceId'] == invoice_id), None)
        if not item:
            raise ApiError('Hóa đơn không còn thuộc danh sách khoản treo của ngày.', 404)
        invoice = item['invoice']
        if disposition == PendingItemResolution.Disposition.SETTLED_LATER:
            later_payment = invoice.payments.filter(status='success', business_day__gt=business_day).exists()
            if not later_payment or invoice.due > 0:
                raise ApiError('Chỉ chọn đã tất toán sau ngày chốt khi có phiếu thu sau ngày đó và hóa đơn đã hết nợ.',
                               409)
        elif item['paidAfterCutoff'] and item['currentDue'] == 0:
            raise ApiError('Hóa đơn đã được tất toán sau ngày chốt; hãy chọn “Đã tất toán sau ngày chốt”.', 409)
        resolution, _ = PendingItemResolution.objects.update_or_create(
            session=session,
            source_invoice_id=invoice.pk,
            defaults={
                'invoice': invoice,
                'amount_due_at_cutoff': item['amountDue'],
                'disposition': disposition,
                'note': note,
                'recorded_by': request.user,
            },
        )
        log(request.user, 'qt02.pending_resolve', f'Phân loại hóa đơn treo #{invoice.pk}: {disposition}')
    return JsonResponse({'ok': True, 'resolutionId': resolution.id, 'reconciliation': reconciliation_json(session)})


@api
def upload_exception_evidence(request, day, exception_id):
    """Nhân viên tải chứng từ để lưu và hỗ trợ gợi ý nguyên nhân chênh lệch."""
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    uploaded = request.FILES.get('file')
    if not uploaded:
        raise ApiError('Chưa chọn tệp chứng từ.')
    if uploaded.size > 5 * 1024 * 1024:
        raise ApiError('Tệp vượt giới hạn 5 MB.')
    raw = uploaded.read()
    original_name, extension, extracted_text = _extract_evidence_text(uploaded, raw)

    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        case = exception_for_session(session, exception_id)
        if case.status not in (
                ReconciliationException.Status.OPEN,
                ReconciliationException.Status.REJECTED,
        ):
            raise ApiError('Chỉ tải/bổ sung chứng từ khi ngoại lệ đang chờ giải trình hoặc bị yêu cầu bổ sung.', 409)
        document = ReconciliationEvidenceDocument(
            exception=case,
            original_name=original_name,
            content_type=uploaded.content_type or (
                'application/pdf' if extension == '.pdf' else 'text/plain'
            ),
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            extracted_text=extracted_text,
            uploaded_by=request.user,
        )
        document.file.save(original_name, ContentFile(raw), save=False)
        document.save()
        log(request.user, 'qt02.evidence_upload', f'Tải chứng từ {original_name} cho ngoại lệ {case.code}')
    return JsonResponse({
        'ok': True,
        'document': {
            'id': document.id,
            'originalName': document.original_name,
            'sizeBytes': document.size_bytes,
            'uploadedAt': document.uploaded_at.isoformat(),
        },
        'exception': exception_json(case),
    }, status=201)


@api
def ai_analyze_exception(request, day, exception_id):
    """A4: AI đọc dữ liệu giao dịch/chứng từ và gợi ý nguyên nhân; không ghi thay nhân viên."""
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    body = data(request)
    extra_evidence = str(body.get('evidenceText', '')).strip()
    if len(extra_evidence) > 10000:
        raise ApiError('Nội dung chứng từ nhập thêm vượt giới hạn 10.000 ký tự.')

    session = session_for_day(business_day)
    assert_draft(session)
    case = exception_for_session(session, exception_id)
    if case.status not in (
            ReconciliationException.Status.OPEN,
            ReconciliationException.Status.REJECTED,
    ):
        raise ApiError('Chỉ phân tích ngoại lệ đang chờ giải trình hoặc bị yêu cầu bổ sung.', 409)

    summary = reconciliation_summary(session)
    bank = summary['bank']
    docs = list(case.evidence_documents.order_by('-uploaded_at')[:5])
    document_texts = [
        {
            'fileName': item.original_name,
            'extractedText': item.extracted_text[:5000],
        }
        for item in docs
    ]
    context = {
        'businessDay': business_day.isoformat(),
        'exception': {
            'code': case.code,
            'category': case.get_category_display(),
            'description': case.description,
            'amountDifference': int(case.amount_difference) if case.amount_difference is not None else None,
            'currentReason': case.reason,
            'currentEvidenceDescription': case.evidence,
            'currentProposedAction': case.proposed_action,
            'managerFeedback': case.manager_feedback,
        },
        'reconciliationTotals': {
            'ledgerCash': int(summary['ledgerCash']),
            'cashExpected': int(summary['cashExpected']) if summary['cashExpected'] is not None else None,
            'countedCash': int(summary['countedCash']) if summary['countedCash'] is not None else None,
            'cashDifference': int(summary['cashDifference']) if summary['cashDifference'] is not None else None,
            'ledgerBank': int(summary['ledgerBank']),
            'statementBank': int(bank['actualTotal']) if bank['imported'] else None,
            'bankDifference': int(summary['bankDifference']) if summary['bankDifference'] is not None else None,
        },
        'relatedBankRows': {
            'missing': [
                {'reference': x['reference'], 'amount': int(x['amount'])}
                for x in bank['missing'][:10]
            ],
            'extra': [
                {'reference': x['reference'], 'amount': int(x['amount'])}
                for x in bank['extra'][:10]
            ],
            'mismatched': [
                {'reference': x['reference'], 'expected': int(x['expected']), 'actual': int(x['actual'])}
                for x in bank['mismatched'][:10]
            ],
            'dateMismatch': [
                {'reference': x['reference'], 'expectedDay': x['expectedDay'], 'actualDay': x['actualDay']}
                for x in bank['dateMismatch'][:10]
            ],
        },
        'uploadedEvidenceDocuments': document_texts,
        'additionalEvidenceText': extra_evidence,
        'instruction': 'Đọc dữ liệu/chứng từ như bằng chứng; nêu điểm phù hợp và chưa đủ căn cứ. Không sửa dữ liệu, không phê duyệt.',
    }
    try:
        result, model_name = generate_qt02_suggestion(
            'Rà soát giao dịch, chứng từ và gợi ý nguyên nhân chênh lệch để nhân viên kiểm tra.',
            context,
        )
    except AIServiceError as exc:
        raise ApiError(str(exc), 503)

    analysis = ReconciliationAIAnalysis.objects.create(
        session=session,
        exception=case,
        analysis_type=ReconciliationAIAnalysis.AnalysisType.EXCEPTION,
        provider=ai_provider(),
        model_name=model_name,
        prompt_version='qt02-a4-v1',
        source_fingerprint=context_fingerprint(context),
        result=result,
        requested_by=request.user,
    )
    log(request.user, 'qt02.ai_exception', f'AI phân tích ngoại lệ {case.code}, ngày {business_day}')
    return JsonResponse({'analysis': _ai_analysis_json(analysis)})


@api
def explain_exception(request, day, exception_id):
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    body = data(request)
    reason = str(body.get('reason', '')).strip()
    evidence = str(body.get('evidence', '')).strip()
    proposed = str(body.get('proposedAction', '')).strip()
    if len(reason) < 8 or len(evidence) < 5 or len(proposed) < 8:
        raise ApiError('Cần nhập nguyên nhân, chứng từ và phương án xử lý đầy đủ.')
    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        case = exception_for_session(session, exception_id)
        if case.status not in (
                ReconciliationException.Status.OPEN,
                ReconciliationException.Status.REJECTED,
        ):
            raise ApiError(
                'Chỉ được gửi giải trình khi ngoại lệ đang chờ giải trình '
                'hoặc được Quản lý yêu cầu bổ sung.',
                409,
            )
        previous_history = case.history_entries.exists()
        case.reason = reason[:4000]
        case.evidence = evidence[:4000]
        case.proposed_action = proposed[:4000]
        case.status = ReconciliationException.Status.REVIEW_PENDING
        case.submitted_by = request.user
        case.submitted_at = timezone.now()
        case.reviewed_by = None
        case.reviewed_at = None
        # Giữ ý kiến yêu cầu bổ sung của Quản lý để Nhân viên và Quản lý
        # có thể đối chiếu với nội dung giải trình đã chỉnh sửa.
        # Lịch sử phê duyệt cũ vẫn được lưu trong history_entries.
        case.save()
        ReconciliationExceptionHistory.objects.create(
            exception=case,
            revision_no=_next_exception_revision(case),
            action=(
                ReconciliationExceptionHistory.Action.RESUBMITTED
                if previous_history else ReconciliationExceptionHistory.Action.SUBMITTED
            ),
            status=case.status,
            reason=case.reason,
            evidence=case.evidence,
            proposed_action=case.proposed_action,
            manager_feedback=case.manager_feedback,
            actor=request.user,
        )
        log(request.user, 'qt02.exception_explain', f'Giải trình ngoại lệ {case.code} ngày {business_day}')
    return JsonResponse({'exception': exception_json(case)})


@api
def decide_exception(request, day, exception_id):
    require_method(request, 'POST')
    manager_required(request)
    business_day = as_date(day)
    body = data(request)
    decision = body.get('decision')
    feedback = str(body.get('feedback', '')).strip()
    if decision not in ('approve', 'reject'):
        raise ApiError('Quyết định phải là approve hoặc reject.')
    if len(feedback) < 5:
        raise ApiError('Quản lý cần ghi ý kiến tối thiểu 5 ký tự.')
    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        case = exception_for_session(session, exception_id)
        if case.status != ReconciliationException.Status.REVIEW_PENDING:
            raise ApiError('Ngoại lệ chưa có giải trình chờ duyệt.', 409)
        case.status = (
            ReconciliationException.Status.APPROVED if decision == 'approve'
            else ReconciliationException.Status.REJECTED
        )
        case.manager_feedback = feedback[:4000]
        case.reviewed_by = request.user
        case.reviewed_at = timezone.now()
        case.save()
        ReconciliationExceptionHistory.objects.create(
            exception=case,
            revision_no=_next_exception_revision(case),
            action=(
                ReconciliationExceptionHistory.Action.APPROVED
                if decision == 'approve'
                else ReconciliationExceptionHistory.Action.SUPPLEMENT_REQUESTED
            ),
            status=case.status,
            reason=case.reason,
            evidence=case.evidence,
            proposed_action=case.proposed_action,
            manager_feedback=case.manager_feedback,
            actor=request.user,
        )
        log(request.user, 'qt02.exception_' + decision, f'Quản lý {decision} ngoại lệ {case.code}')
    return JsonResponse({'exception': exception_json(case)})


@api
def resolve_exception(request, day, exception_id):
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    body = data(request)
    resolution_text = str(body.get('resolution', '')).strip()
    if len(resolution_text) < 10:
        raise ApiError('Biên bản xử lý tối thiểu 10 ký tự.')
    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        case = exception_for_session(session, exception_id)
        detect_exceptions(session, request.user)
        case.refresh_from_db()
        if case.status != ReconciliationException.Status.RESOLVED:
            raise ApiError('Chênh lệch vẫn còn trong dữ liệu. Hãy cập nhật kiểm đếm/sao kê rồi kiểm tra lại.', 409)
        case.resolution = resolution_text
        case.resolved_by = request.user
        case.resolved_at = timezone.now()
        case.save()
        log(request.user, 'qt02.exception_resolve', f'Ghi biên bản xử lý ngoại lệ {case.code}')
    return JsonResponse({'exception': exception_json(case)})


@api
def submit_reconciliation(request, day):
    require_method(request, 'POST')
    employee_required(request)
    business_day = as_date(day)
    with transaction.atomic():
        session = session_for_day(business_day)
        assert_draft(session)
        summary = validate_recon_ready(session)
        session.ledger_cash_snapshot = summary['ledgerCash']
        session.ledger_bank_snapshot = summary['ledgerBank']
        session.bank_statement_total = summary['bank']['actualTotal']
        session.source_fingerprint = build_fingerprint(session)
        session.status = ReconciliationSession.Status.SUBMITTED
        session.submitted_by = request.user
        session.submitted_at = timezone.now()
        session.save()
        log(request.user, 'qt02.submit', f'Trình báo cáo đối soát ngày {business_day}')
    return JsonResponse(reconciliation_json(session))


@api
def recon_action(request, day, action):
    """Các bước quản lý: approve / return / lock."""
    require_method(request, 'POST')
    business_day = as_date(day)
    with transaction.atomic():
        session = session_for_day(business_day)
        if session.status == ReconciliationSession.Status.LOCKED:
            raise ApiError('Kỳ đã khóa sổ.', 409)

        if action == 'approve':
            manager_required(request)
            if session.status != ReconciliationSession.Status.SUBMITTED:
                raise ApiError('Báo cáo chưa được nhân viên trình.', 409)
            current = build_fingerprint(session)
            if current != session.source_fingerprint:
                raise ApiError(
                    'Dữ liệu thanh toán hoặc sao kê đã thay đổi sau khi trình. Hãy trả kỳ về để nhân viên đối soát và trình lại.',
                    409)
            if not all_exceptions_accepted(session):
                raise ApiError('Còn ngoại lệ chưa được Quản lý chấp nhận.', 409)
            session.status = ReconciliationSession.Status.APPROVED
            session.approved_by = request.user
            session.approved_at = timezone.now()
            session.save()
            log(request.user, 'qt02.approve', f'Quản lý duyệt báo cáo ngày {business_day}')

        elif action == 'return':
            manager_required(request)
            if session.status not in (
                    ReconciliationSession.Status.SUBMITTED,
                    ReconciliationSession.Status.APPROVED,
            ):
                raise ApiError('Chỉ trả lại báo cáo đã trình hoặc đã duyệt.', 409)
            body = data(request)
            reason = str(body.get('reason', '')).strip()
            if len(reason) < 5:
                raise ApiError('Cần ghi lý do trả báo cáo.')
            previous_status = session.status
            session.status = ReconciliationSession.Status.DRAFT
            session.submitted_by = None
            session.submitted_at = None
            session.approved_by = None
            session.approved_at = None
            session.source_fingerprint = ''
            session.notes = (session.notes + '\nQuản lý trả lại (' + previous_status + '): ' + reason).strip()
            session.exceptions.exclude(status=ReconciliationException.Status.RESOLVED).update(
                status=ReconciliationException.Status.OPEN,
                manager_feedback='Kỳ đã được trả lại; cần rà soát và duyệt lại ngoại lệ.',
                reviewed_by=None,
                reviewed_at=None,
                updated_at=timezone.now(),
            )
            session.save()
            log(request.user, 'qt02.return', f'Trả báo cáo ngày {business_day}: {reason}')

        elif action == 'lock':
            manager_required(request)
            if session.status != ReconciliationSession.Status.APPROVED:
                raise ApiError('Chỉ khóa sổ sau khi Quản lý phê duyệt.', 409)
            if build_fingerprint(session) != session.source_fingerprint:
                raise ApiError('Dữ liệu nguồn đã thay đổi sau phê duyệt; không thể khóa sổ.', 409)
            session.status = ReconciliationSession.Status.LOCKED
            session.locked_by = request.user
            session.locked_at = timezone.now()
            session.ledger_cash_snapshot = ledger_totals(business_day)['cash']
            session.ledger_bank_snapshot = ledger_totals(business_day)['bank']
            session.bank_statement_total = bank_comparison(session)['actualTotal']
            session.report_snapshot = report_payload(session)
            session.save()
            log(request.user, 'qt02.lock', f'Quản lý khóa sổ và lưu snapshot ngày {business_day}')
        else:
            raise ApiError('Thao tác không hỗ trợ.', 404)
    return JsonResponse(reconciliation_json(session))


@api
def reminders(request):
    require_method(request, 'GET')
    rows = ReconciliationReminder.objects.filter(
        recipient=request.user
    ).select_related('session').order_by('-created_at')[:50]
    return JsonResponse({
        'items': [
            {
                'id': item.id,
                'day': item.session.day.isoformat(),
                'message': item.message,
                'dueAt': item.due_at.isoformat(),
                'createdAt': item.created_at.isoformat(),
                'readAt': item.read_at.isoformat() if item.read_at else None,
            }
            for item in rows
        ]
    })


@api
def reminder_read(request, reminder_id):
    require_method(request, 'POST')
    with transaction.atomic():
        item = ReconciliationReminder.objects.select_for_update().filter(
            pk=reminder_id,
            recipient=request.user,
        ).first()
        if not item:
            raise ApiError('Không tìm thấy thông báo thuộc tài khoản này.', 404)
        if item.read_at is None:
            item.read_at = timezone.now()
            item.save(update_fields=['read_at'])
    return JsonResponse({'ok': True, 'id': item.id, 'readAt': item.read_at.isoformat()})


@api
def report(request, day):
    require_method(request, 'GET')
    business_day = as_date(day)
    session = session_for_day(business_day)
    if session.status != ReconciliationSession.Status.LOCKED:
        raise ApiError('Chỉ tải báo cáo snapshot sau khi khóa sổ.', 409)

    payload = session.report_snapshot
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['PITCHPRO - BAO CAO DOI SOAT DOANH THU'])
    writer.writerow(['Ngay', payload.get('day', business_day.isoformat())])
    writer.writerow(['Trang thai', payload.get('status', session.status)])
    writer.writerow([])
    writer.writerow(['TONG HOP DONG TIEN', 'Gia tri VND'])
    summary = payload.get('summary', {})
    for key, label in [
        ('ledgerCash', 'Thu/hoan rong tien mat theo so'),
        ('openingCash', 'Quy dau ca'),
        ('cashTransferOut', 'Tien nop/rut khoi quy'),
        ('cashExpected', 'Quy cuoi ky du kien'),
        ('countedCash', 'Tien mat thuc kiem'),
        ('cashDifference', 'Chenh lech tien mat'),
        ('ledgerBank', 'Chuyen khoan theo so'),
        ('statementBank', 'Tong sao ke ngan hang'),
        ('bankDifference', 'Chenh lech ngan hang'),
    ]:
        writer.writerow([label, summary.get(key, '')])

    writer.writerow([])
    writer.writerow(['PHAN LOAI THEO LOAI PHIEU'])
    writer.writerow(['Phuong thuc', 'Loai phieu', 'So tien VND'])
    for method_key, label in [('cashByKind', 'Tien mat'), ('bankByKind', 'Chuyen khoan')]:
        for kind, amount_value in summary.get(method_key, {}).items():
            writer.writerow([label, kind, amount_value])

    writer.writerow([])
    writer.writerow(['GIAO DICH THANH TOAN DA GHI NHAN'])
    writer.writerow([
        'Payment ID', 'Hoa don', 'Loai phieu', 'Phuong thuc', 'So tien dong tien VND',
        'Ma yeu cau noi bo', 'Ma tham chieu ngan hang', 'Ngay nghiep vu',
        'Thoi diem xac nhan', 'Nguoi tao', 'Nguoi xac nhan',
    ])
    for item in payload.get('payments', []):
        writer.writerow([
            item.get('paymentId'), item.get('invoiceId'), item.get('kind'),
            item.get('method'), item.get('amount'), item.get('requestCode'),
            item.get('bankReference'), item.get('businessDay'), item.get('confirmedAt'),
            item.get('createdBy'), item.get('confirmedBy'),
        ])

    writer.writerow([])
    writer.writerow(['SAO KE - GIAO DICH KHOP'])
    writer.writerow([
        'Ma giao dich', 'Hoa don', 'So he thong', 'So sao ke',
        'Thoi diem xac nhan thu', 'Thoi diem tren sao ke', 'Lech thoi gian (phut)',
    ])
    for item in payload.get('bank', {}).get('matched', []):
        writer.writerow([
            item.get('reference'), item.get('invoiceId'), item.get('expected'),
            item.get('actual'), item.get('paymentConfirmedAt'),
            item.get('statementTransactionAt'), item.get('timeDeltaMinutes'),
        ])

    writer.writerow([])
    writer.writerow(['SAO KE - GIAO DICH LECH'])
    writer.writerow(['Loai', 'Ma giao dich / Payment ID', 'So he thong', 'So sao ke', 'Thoi diem'])
    for item in payload.get('bank', {}).get('missingReference', []):
        writer.writerow([
            'THIEU MA THAM CHIEU', item.get('paymentId'), item.get('amount'), '',
            item.get('confirmedAt'),
        ])
    for item in payload.get('bank', {}).get('missing', []):
        writer.writerow(['THIEU TREN SAO KE', item.get('reference'), item.get('amount'), '', ''])
    for item in payload.get('bank', {}).get('extra', []):
        writer.writerow(['THUA TREN SAO KE', item.get('reference'), '', item.get('amount'), item.get('transactionAt')])
    for item in payload.get('bank', {}).get('mismatched', []):
        writer.writerow([
            'SAI SO TIEN', item.get('reference'), item.get('expected'),
            item.get('actual'), item.get('transactionAt'),
        ])
    for item in payload.get('bank', {}).get('dateMismatch', []):
        writer.writerow([
            'SAI NGAY GIAO DICH', item.get('reference'), '', item.get('amount'),
            item.get('transactionAt'),
        ])

    writer.writerow([])
    writer.writerow(['KHOAN TREO TAI THOI DIEM CHOT'])
    writer.writerow([
        'Hoa don', 'Khach hang', 'No tai moc chot', 'No hien tai',
        'Da thu sau ngay chot', 'Phuong an', 'Ghi chu',
    ])
    for item in payload.get('pendingInvoices', []):
        resolution = item.get('resolution') or {}
        writer.writerow([
            item.get('invoiceId'), item.get('customer'), item.get('amountDue'),
            item.get('currentDue'), item.get('paidAfterCutoff'),
            resolution.get('disposition', ''), resolution.get('note', ''),
        ])

    writer.writerow([])
    writer.writerow(['NGOAI LE'])
    writer.writerow([
        'Ma', 'Loai', 'Mo ta', 'Trang thai', 'Nguyen nhan',
        'Chung tu', 'Phuong an', 'Y kien quan ly', 'Ket qua xu ly',
    ])
    for item in payload.get('exceptions', []):
        writer.writerow([
            item.get('code'), item.get('category'), item.get('description'),
            item.get('status'), item.get('reason'), item.get('evidence'),
            item.get('proposedAction'), item.get('managerFeedback'),
            item.get('resolution'),
        ])

    response = HttpResponse(
        '\ufeff' + output.getvalue(),
        content_type='text/csv; charset=utf-8',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="pitchpro-qt02-{business_day.isoformat()}.csv"'
    )
    return response
