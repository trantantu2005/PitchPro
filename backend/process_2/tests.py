import json
import os
import tempfile
from decimal import Decimal
from datetime import timedelta
from django.core.management import call_command

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
from django.utils import timezone

from operations.models import Customer, Invoice, InvoiceLine, Payment
from process_2.models import (
    BankStatement, BankStatementLine, PendingItemResolution,
    ReconciliationException, ReconciliationExceptionHistory,
    ReconciliationAIAnalysis, ReconciliationEvidenceDocument,
    ReconciliationReminder, ReconciliationSession,
)


class ProcessTwoReconciliationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(username='staff', password='test-password')
        self.manager = User.objects.create_user(username='manager', password='test-password')
        group, _ = Group.objects.get_or_create(name='Manager')
        staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.manager.groups.add(group)
        self.staff.groups.add(staff_group)
        self.day = timezone.localdate() - timedelta(days=1)
        self.customer = Customer.objects.create(name='FC Demo', phone='0900000001')
        self.invoice = Invoice.objects.create(customer=self.customer, customer_name='FC Demo', created_by=self.staff)
        Payment.objects.create(
            invoice=self.invoice, kind='settlement', method='cash', channel='manual',
            amount=Decimal('100000'), status='success', request_code='CASH-100',
            business_day=self.day, created_by=self.staff, confirmed_by=self.staff,
            confirmed_at=timezone.now(),
        )
        Payment.objects.create(
            invoice=self.invoice, kind='settlement', method='bank', channel='manual',
            amount=Decimal('250000'), status='success', request_code='BANK-250',
            bank_reference='BANK-REF-250', business_day=self.day,
            created_by=self.staff, confirmed_by=self.staff, confirmed_at=timezone.now(),
        )

    def post(self, url, body=None, user=None):
        self.client.force_login(user or self.staff)
        return self.client.post(url, data=json.dumps(body or {}), content_type='application/json')

    def open_session(self):
        response = self.post('/api/reconciliation/', {'date': self.day.isoformat()})
        self.assertEqual(response.status_code, 201, response.content)
        return ReconciliationSession.objects.get(day=self.day)

    def setup_matching_sources(self, session):
        cash = self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 100000,
            'notes': 'Biên bản kiểm đếm quỹ cuối ngày.',
        })
        self.assertEqual(cash.status_code, 200, cash.content)
        bank = self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo',
            'rows': [{'reference': 'BANK-REF-250', 'amount': 250000, 'description': 'Thanh toán demo'}],
        })
        self.assertEqual(bank.status_code, 200, bank.content)

    def test_happy_path_submit_approve_lock(self):
        session = self.open_session()
        self.setup_matching_sources(session)
        detect = self.post(f'/api/reconciliation/{self.day}/detect/', {})
        self.assertEqual(detect.status_code, 200, detect.content)
        submit = self.post(f'/api/reconciliation/{self.day}/submit/', {})
        self.assertEqual(submit.status_code, 200, submit.content)
        denied = self.post(f'/api/reconciliation/{self.day}/approve/', {}, user=self.staff)
        self.assertEqual(denied.status_code, 403)
        approved = self.post(f'/api/reconciliation/{self.day}/approve/', {}, user=self.manager)
        self.assertEqual(approved.status_code, 200, approved.content)
        locked = self.post(f'/api/reconciliation/{self.day}/lock/', {}, user=self.manager)
        self.assertEqual(locked.status_code, 200, locked.content)
        session.refresh_from_db()
        self.assertEqual(session.status, 'locked')
        self.assertTrue(session.report_snapshot)
        self.assertEqual(len(session.report_snapshot.get('payments', [])), 2)
        self.assertTrue(session.report_snapshot['payments'][0]['confirmedAt'])

    def test_bank_reference_mismatch_requires_explanation_and_manager_decision(self):
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 100000,
            'notes': 'Biên bản kiểm đếm quỹ cuối ngày.',
        })
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo',
            'rows': [{'reference': 'WRONG-REF-250', 'amount': 250000}],
        })
        detected = self.post(f'/api/reconciliation/{self.day}/detect/', {})
        self.assertEqual(detected.status_code, 200)
        cases = list(ReconciliationException.objects.filter(session=session).order_by('category'))
        self.assertGreaterEqual(len(cases), 2)
        missing_case = next(x for x in cases if x.category == ReconciliationException.Category.BANK_MISSING)
        for case in cases:
            explain = self.post(f'/api/reconciliation/{self.day}/exceptions/{case.id}/explain/', {
                'reason': 'Đã kiểm tra giao dịch chuyển khoản trong ngày.',
                'evidence': 'Sao kê ngân hàng mã WRONG-REF-250.',
                'proposedAction': 'Đối chiếu lại mã tham chiếu với chứng từ thanh toán gốc.',
            })
            self.assertEqual(explain.status_code, 200, explain.content)
            decision = self.post(f'/api/reconciliation/{self.day}/exceptions/{case.id}/decision/', {
                'decision': 'approve', 'feedback': 'Chấp nhận phương án xác minh có chứng từ.',
            }, user=self.manager)
            self.assertEqual(decision.status_code, 200, decision.content)
        self.assertEqual(missing_case.category, ReconciliationException.Category.BANK_MISSING)
        submitted = self.post(f'/api/reconciliation/{self.day}/submit/', {})
        self.assertEqual(submitted.status_code, 200, submitted.content)


    def test_cash_shortage_uses_negative_difference(self):
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 90000,
            'notes': 'Biên bản kiểm quỹ phát hiện thiếu tiền.',
        })
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo',
            'rows': [{'reference': 'BANK-REF-250', 'amount': 250000}],
        })
        detected = self.post(f'/api/reconciliation/{self.day}/detect/', {})
        self.assertEqual(detected.status_code, 200, detected.content)
        case = ReconciliationException.objects.get(
            session=session, category=ReconciliationException.Category.CASH_SHORTAGE
        )
        self.assertEqual(case.amount_difference, Decimal('-10000'))

    def test_changed_payment_after_submit_blocks_manager_approval(self):
        session = self.open_session()
        self.setup_matching_sources(session)
        self.post(f'/api/reconciliation/{self.day}/detect/', {})
        submitted = self.post(f'/api/reconciliation/{self.day}/submit/', {})
        self.assertEqual(submitted.status_code, 200, submitted.content)
        Payment.objects.create(
            invoice=self.invoice, kind='settlement', method='cash', channel='manual',
            amount=Decimal('10000'), status='success', request_code='CASH-LATE',
            business_day=self.day, created_by=self.staff, confirmed_by=self.staff,
            confirmed_at=timezone.now(),
        )
        approved = self.post(f'/api/reconciliation/{self.day}/approve/', {}, user=self.manager)
        self.assertEqual(approved.status_code, 409)


    def test_bank_payment_without_real_reference_is_flagged(self):
        Payment.objects.create(
            invoice=self.invoice,
            kind='settlement',
            method='bank',
            channel='manual',
            amount=Decimal('50000'),
            status='success',
            request_code='BANK-NO-REFERENCE',
            bank_reference=None,
            business_day=self.day,
            created_by=self.staff,
            confirmed_by=self.staff,
            confirmed_at=timezone.now(),
        )
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 100000,
            'notes': 'Biên bản kiểm đếm quỹ cuối ngày.',
        })
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo',
            'rows': [{'reference': 'BANK-REF-250', 'amount': 250000}],
        })
        detected = self.post(f'/api/reconciliation/{self.day}/detect/', {})
        self.assertEqual(detected.status_code, 200, detected.content)
        self.assertTrue(ReconciliationException.objects.filter(
            session=session,
            category=ReconciliationException.Category.BANK_REFERENCE_MISSING,
        ).exists())

    def test_bank_statement_wrong_business_date_creates_exception(self):
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 100000,
            'notes': 'Biên bản kiểm đếm quỹ cuối ngày.',
        })
        wrong_day = self.day + timedelta(days=1)
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo',
            'rows': [{
                'reference': 'BANK-REF-250',
                'amount': 250000,
                'transactionAt': f'{wrong_day.isoformat()}T09:30:00+07:00',
            }],
        })
        detected = self.post(f'/api/reconciliation/{self.day}/detect/', {})
        self.assertEqual(detected.status_code, 200, detected.content)
        self.assertTrue(ReconciliationException.objects.filter(
            session=session,
            category=ReconciliationException.Category.BANK_DATE_MISMATCH,
        ).exists())

    def test_late_settlement_requires_settled_later_disposition(self):
        invoice = Invoice.objects.create(
            customer=self.customer,
            customer_name='FC Treo',
            created_by=self.staff,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            kind='rental',
            description='Thuê sân demo',
            quantity=1,
            unit_price=Decimal('500000'),
        )
        Payment.objects.create(
            invoice=invoice,
            kind='settlement',
            method='cash',
            channel='manual',
            amount=Decimal('200000'),
            status='success',
            request_code='PENDING-PARTIAL',
            business_day=self.day,
            created_by=self.staff,
            confirmed_by=self.staff,
            confirmed_at=timezone.now(),
        )
        session = self.open_session()
        PendingItemResolution.objects.create(
            session=session,
            invoice=invoice,
            source_invoice_id=invoice.pk,
            amount_due_at_cutoff=Decimal('300000'),
            disposition=PendingItemResolution.Disposition.CARRY_FORWARD,
            note='Chuyển phần còn phải thu sang kỳ sau.',
            recorded_by=self.staff,
        )
        Payment.objects.create(
            invoice=invoice,
            kind='settlement',
            method='cash',
            channel='manual',
            amount=Decimal('300000'),
            status='success',
            request_code='PENDING-PAID-LATER',
            business_day=self.day + timedelta(days=1),
            created_by=self.staff,
            confirmed_by=self.staff,
            confirmed_at=timezone.now(),
        )
        from process_2.services import unresolved_pending
        self.assertIn(invoice.pk, unresolved_pending(session))
        resolution = session.pending_resolutions.get(source_invoice_id=invoice.pk)
        resolution.disposition = PendingItemResolution.Disposition.SETTLED_LATER
        resolution.save(update_fields=['disposition'])
        self.assertNotIn(invoice.pk, unresolved_pending(session))

    def test_overdue_submitted_report_creates_manager_reminder(self):
        session = self.open_session()
        session.status = ReconciliationSession.Status.SUBMITTED
        session.submitted_by = self.staff
        session.submitted_at = timezone.now() - timedelta(minutes=11)
        session.save(update_fields=['status', 'submitted_by', 'submitted_at'])
        call_command('dispatch_qt02_reminders')
        self.assertTrue(ReconciliationReminder.objects.filter(
            session=session, recipient=self.manager,
            kind='manager_approval_overdue',
        ).exists())
        self.assertFalse(ReconciliationReminder.objects.filter(
            session=session, recipient=self.staff,
        ).exists())

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'test-model'})
    @patch('process_2.views.generate_qt02_suggestion')
    def test_ai_exception_analysis_reads_evidence_but_does_not_decide(self, mocked_ai):
        mocked_ai.return_value = ({
            'summary': 'Mã giao dịch trên sổ không xuất hiện trong sao kê.',
            'possible_causes': ['Sai mã tham chiếu khi nhập phiếu.'],
            'supporting_evidence': ['Mã trên sao kê khác mã trong sổ.'],
            'checks_to_perform': ['Đối chiếu biên nhận và lịch sử ngân hàng.'],
            'suggested_reason': 'Có thể mã tham chiếu được nhập chưa chính xác.',
            'suggested_action': 'Yêu cầu nhân viên kiểm tra chứng từ gốc.',
            'uncertainties': ['Chưa có chứng từ ngân hàng gốc.'],
            'safety_note': 'AI chỉ gợi ý.',
        }, 'test-model')

        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 100000,
            'notes': 'Biên bản kiểm quỹ cuối ngày.',
        })
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo',
            'rows': [{'reference': 'WRONG-REF', 'amount': 250000}],
        })
        self.post(f'/api/reconciliation/{self.day}/detect/', {})
        case = ReconciliationException.objects.filter(
            session=session,
            category=ReconciliationException.Category.BANK_MISSING,
        ).first()
        self.assertIsNotNone(case)
        old_status = case.status
        response = self.post(
            f'/api/reconciliation/{self.day}/exceptions/{case.id}/ai/',
            {'evidenceText': 'Biên nhận giao dịch có mã BANK-REF-250.'},
        )
        self.assertEqual(response.status_code, 200, response.content)
        case.refresh_from_db()
        self.assertEqual(case.status, old_status)
        self.assertEqual(case.reason, '')
        analysis = ReconciliationAIAnalysis.objects.get(exception=case)
        self.assertEqual(analysis.result['summary'], 'Mã giao dịch trên sổ không xuất hiện trong sao kê.')
        mocked_ai.assert_called_once()
        context = mocked_ai.call_args.args[1]
        self.assertEqual(context['additionalEvidenceText'], 'Biên nhận giao dịch có mã BANK-REF-250.')

    def test_only_exception_ai_endpoint_is_registered(self):
        from django.urls import resolve, Resolver404
        for path in (
            '/api/invoices/1/ai/cancellation/',
            '/api/invoices/1/ai/discrepancy/',
            f'/api/reconciliation/{self.day}/ai/pending/',
        ):
            with self.assertRaises(Resolver404):
                resolve(path)
        match = resolve(f'/api/reconciliation/{self.day}/exceptions/1/ai/')
        self.assertEqual(match.url_name, 'ai-exception')

    def test_only_remaining_ai_requires_employee_and_configured_provider(self):
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 50000,
            'notes': 'Kiểm quỹ thử nghiệm để tạo chênh lệch.',
        })
        self.post(f'/api/reconciliation/{self.day}/detect/', {})
        case = ReconciliationException.objects.filter(session=session).first()
        self.assertIsNotNone(case)
        url = f'/api/reconciliation/{self.day}/exceptions/{case.id}/ai/'
        with patch.dict(os.environ, {'QT02_AI_PROVIDER': 'openai', 'OPENAI_API_KEY': ''}):
            missing_key = self.post(url, {'evidenceText': 'Bằng chứng kiểm thử.'})
        self.assertEqual(missing_key.status_code, 503, missing_key.content)
        with patch.dict(os.environ, {'QT02_AI_PROVIDER': 'openai', 'OPENAI_API_KEY': 'mock-test'}):
            denied_manager = self.post(url, {'evidenceText': 'Bằng chứng kiểm thử.'}, user=self.manager)
        self.assertEqual(denied_manager.status_code, 403, denied_manager.content)

    def test_exception_evidence_txt_upload_extracts_text(self):
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 90000,
            'notes': 'Biên bản kiểm quỹ phát hiện thiếu tiền.',
        })
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo', 'rows': [{'reference': 'BANK-REF-250', 'amount': 250000}],
        })
        self.post(f'/api/reconciliation/{self.day}/detect/', {})
        case = ReconciliationException.objects.filter(
            session=session, category=ReconciliationException.Category.CASH_SHORTAGE,
        ).first()
        self.assertIsNotNone(case)
        upload = SimpleUploadedFile(
            'bien-ban-kiem-quy.txt',
            'Biên bản: tiền thực kiểm thiếu 10.000 đồng.'.encode('utf-8'),
            content_type='text/plain',
        )
        response = self.client.post(
            f'/api/reconciliation/{self.day}/exceptions/{case.id}/evidence/',
            {'file': upload},
        )
        self.assertEqual(response.status_code, 201, response.content)
        document = ReconciliationEvidenceDocument.objects.get(exception=case)
        self.assertIn('thiếu 10.000', document.extracted_text)
        document.file.delete(save=False)

    def test_exception_explanation_and_manager_decision_are_versioned(self):
        session = self.open_session()
        self.post(f'/api/reconciliation/{self.day}/cash/', {
            'openingCash': 0, 'cashTransferOut': 0, 'countedCash': 90000,
            'notes': 'Biên bản kiểm quỹ phát hiện thiếu tiền.',
        })
        self.post(f'/api/reconciliation/{self.day}/bank-statement/', {
            'source': 'Sao kê demo', 'rows': [{'reference': 'BANK-REF-250', 'amount': 250000}],
        })
        self.post(f'/api/reconciliation/{self.day}/detect/', {})
        case = ReconciliationException.objects.get(
            session=session, category=ReconciliationException.Category.CASH_SHORTAGE,
        )
        explain = self.post(f'/api/reconciliation/{self.day}/exceptions/{case.id}/explain/', {
            'reason': 'Có thể ghi nhận thiếu tiền do nộp quỹ chưa kịp thời.',
            'evidence': 'Biên bản kiểm đếm cuối ngày.',
            'proposedAction': 'Đối chiếu phiếu nộp quỹ và camera quầy thu ngân.',
        })
        self.assertEqual(explain.status_code, 200, explain.content)
        decision = self.post(f'/api/reconciliation/{self.day}/exceptions/{case.id}/decision/', {
            'decision': 'reject', 'feedback': 'Bổ sung biên nhận nộp tiền vào ngân hàng.',
        }, user=self.manager)
        self.assertEqual(decision.status_code, 200, decision.content)
        history = list(ReconciliationExceptionHistory.objects.filter(exception=case).order_by('revision_no'))
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].action, ReconciliationExceptionHistory.Action.SUBMITTED)
        self.assertEqual(history[1].action, ReconciliationExceptionHistory.Action.SUPPLEMENT_REQUESTED)

