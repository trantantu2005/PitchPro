import json
from datetime import datetime, time, timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from operations.models import Booking, FootballField, Invoice, Payment, Product


class ProcessOneFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='nhanvien', password='test-strong-password')
        staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.user.groups.add(staff_group)
        self.client.force_login(self.user)
        self.pitch = FootballField.objects.create(name='Sân 01', field_type=5, hourly_rate=200000)
        self.water = Product.objects.create(name='Nước suối 500ml', price=10000, stock=20)
        self.day = timezone.localdate()

    def post(self, url, body=None):
        return self.client.post(url, data=json.dumps(body or {}), content_type='application/json')

    def make_booking(self):
        # Kiểm thử nghiệp vụ trong ngày phải độc lập với giờ chạy thực tế.
        pre_booking_time = timezone.make_aware(
            datetime.combine(self.day, time(0, 0)),
            timezone.get_current_timezone(),
        )
        with patch('process_1.views.timezone.localtime', return_value=pre_booking_time):
            return self.post('/api/bookings/', {
                'date': self.day.isoformat(), 'pitchId': self.pitch.pk,
                'start': '00:01', 'end': '23:59',
                'name': 'FC Sông Hàn', 'phone': '0990000010', 'depositRate': 0,
            })

    def test_main_flow_cash(self):
        booked = self.make_booking()
        self.assertEqual(booked.status_code, 201, booked.content)
        booking_id = booked.json()['booking']['id']
        invoice_id = booked.json()['invoice']['id']
        overlap = self.make_booking()
        self.assertEqual(overlap.status_code, 409)

        received = self.post(f'/api/bookings/{booking_id}/check-in/')
        self.assertEqual(received.status_code, 200, received.content)
        sold = self.post(f'/api/invoices/{invoice_id}/items/', {'productId': self.water.id, 'quantity': 2})
        self.assertEqual(sold.status_code, 200, sold.content)
        self.water.refresh_from_db()
        self.assertEqual(self.water.stock, 18)
        finished = self.post(f'/api/bookings/{booking_id}/check-out/', {'earlyCheckout': True})
        self.assertEqual(finished.status_code, 200, finished.content)
        self.assertEqual(finished.json()['invoice']['status'], 'draft')
        finalized = self.post(f'/api/invoices/{invoice_id}/finalize/')
        self.assertEqual(finalized.status_code, 200, finalized.content)
        paid = self.post(f'/api/invoices/{invoice_id}/pay/', {'method': 'cash'})
        self.assertEqual(paid.status_code, 200, paid.content)
        self.assertEqual(paid.json()['invoice']['due'], 0)
        second = self.post(f'/api/invoices/{invoice_id}/pay/', {'method': 'cash'})
        self.assertEqual(second.status_code, 409)

    def test_qr_does_not_collect_before_confirmation(self):
        response = self.make_booking()
        booking_id = response.json()['booking']['id']
        invoice_id = response.json()['invoice']['id']
        self.post(f'/api/bookings/{booking_id}/check-in/')
        self.post(f'/api/bookings/{booking_id}/check-out/', {'earlyCheckout': True})
        finalized = self.post(f'/api/invoices/{invoice_id}/finalize/')
        self.assertEqual(finalized.status_code, 200, finalized.content)
        qr = self.post(f'/api/invoices/{invoice_id}/qr/')
        self.assertEqual(qr.status_code, 201, qr.content)
        self.assertEqual(Payment.objects.filter(status='success').count(), 0)
        invalid = self.post(f'/api/invoices/{invoice_id}/pay/', {'method': 'bank', 'bankReference': 'ABCDE'})
        self.assertEqual(invalid.status_code, 400)
        paid = self.post(f'/api/invoices/{invoice_id}/pay/', {
            'method': 'bank', 'bankReference': 'TEST-BANK-001', 'manuallyVerified': True,
        })
        self.assertEqual(paid.status_code, 200, paid.content)
        self.assertEqual(Payment.objects.filter(status='success').count(), 1)

    def test_cancel_booking_without_ai_keeps_policy_rules(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        future_day = self.day + timedelta(days=3)
        response = self.post('/api/bookings/', {
            'date': future_day.isoformat(), 'pitchId': self.pitch.pk,
            'start': '17:00', 'end': '18:00',
            'name': 'FC Demo Hủy', 'phone': '0990000011', 'depositRate': 0,
        })
        self.assertEqual(response.status_code, 201, response.content)
        booking_id = response.json()['booking']['id']
        invoice_id = response.json()['invoice']['id']
        canceled = self.post(f'/api/bookings/{booking_id}/cancel/', {
            'reasonType': 'personal', 'reason': 'Khách thay đổi lịch tập',
        })
        self.assertEqual(canceled.status_code, 200, canceled.content)
        self.assertTrue(canceled.json()['policyAssessment']['canCancel'])
        self.assertEqual(canceled.json()['booking']['status'], 'cancelled')
        self.assertEqual(Invoice.objects.get(pk=invoice_id).status, 'cancelled')


class CustomerRoleIsolationTests(TestCase):
    """Giai doan 1: khach dang nhap duoc nhung khong vao API QT01/QT02."""

    def setUp(self):
        from operations.models import Customer

        user_model = get_user_model()
        staff_group, _ = Group.objects.get_or_create(name='Staff')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        customer_group, _ = Group.objects.get_or_create(name='Customer')

        self.staff = user_model.objects.create_user('staff_role_test', password='safe-test-pass')
        self.staff.groups.add(staff_group)
        self.manager = user_model.objects.create_user('manager_role_test', password='safe-test-pass')
        self.manager.groups.add(manager_group)
        self.customer = user_model.objects.create_user('customer_role_test', password='safe-test-pass')
        self.customer.groups.add(customer_group)
        self.customer_profile = Customer.objects.create(
            user=self.customer, name='Khach hang A', phone='0991234567',
        )

    def post_json(self, url, body=None):
        return self.client.post(url, data=json.dumps(body or {}), content_type='application/json')

    def test_customer_cannot_read_internal_apis(self):
        self.client.force_login(self.customer)
        for url in ('/api/state/', '/api/bootstrap/', '/api/bookings/',
                    '/api/invoices/', '/api/reconciliation/',
                    '/api/reconciliation/reminders/',
                    '/api/invoices/1/qr/image/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_customer_cannot_modify_internal_data(self):
        self.client.force_login(self.customer)
        urls = (
            '/api/bookings/',
            '/api/stock/restock/',
            '/api/products/',
            '/api/invoices/1/pay/',
            '/api/invoices/1/deposit/',
            '/api/reconciliation/',
            '/api/reconciliation/2026-11-05/approve/',
            '/api/reconciliation/2026-11-05/lock/',
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.post_json(url).status_code, 403)

    def test_customer_can_log_in_but_has_no_internal_access(self):
        self.client.logout()
        response = self.post_json('/api/session/', {
            'username': 'customer_role_test', 'password': 'safe-test-pass',
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['role'], 'Customer')
        self.assertEqual(self.client.get('/api/session/').json()['role'], 'Customer')
        self.assertEqual(self.client.get('/api/state/').status_code, 403)

    def test_staff_and_manager_keep_internal_access(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/api/state/').status_code, 200)
        self.assertEqual(self.client.get('/api/session/').json()['role'], 'Staff')
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/api/state/').status_code, 200)
        self.assertEqual(self.client.get('/api/session/').json()['role'], 'Manager')

    def test_legacy_customer_has_no_user_until_explicitly_linked(self):
        from operations.models import Customer

        legacy = Customer.objects.create(name='Khach dat truc tiep', phone='0997654321')
        self.assertIsNone(legacy.user_id)
        self.assertIsNotNone(self.customer_profile.user_id)

    def test_no_group_or_is_staff_flag_cannot_access_apis(self):
        user_model = get_user_model()
        unassigned = user_model.objects.create_user(
            'unassigned_role_test', password='safe-test-pass', is_staff=True,
        )
        self.client.force_login(unassigned)
        self.assertEqual(self.client.get('/api/state/').status_code, 403)
        self.client.logout()
        response = self.post_json('/api/session/', {
            'username': 'unassigned_role_test', 'password': 'safe-test-pass',
        })
        self.assertEqual(response.status_code, 403)

    def test_conflicting_customer_staff_groups_are_denied(self):
        self.customer.groups.add(Group.objects.get(name='Staff'))
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/api/state/').status_code, 403)

    def test_guest_is_unauthorized(self):
        self.assertEqual(self.client.get('/api/state/').status_code, 401)

    def test_media_documents_are_not_public_in_debug(self):
        import tempfile
        from pathlib import Path
        from django.test import override_settings

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, 'proof.txt').write_text('private evidence', encoding='utf-8')
            with override_settings(DEBUG=True, MEDIA_ROOT=temp_dir):
                self.assertEqual(self.client.get('/media/proof.txt').status_code, 403)
                self.client.force_login(self.customer)
                self.assertEqual(self.client.get('/media/proof.txt').status_code, 403)
                self.client.force_login(self.staff)
                self.assertEqual(self.client.get('/media/proof.txt').status_code, 200)
