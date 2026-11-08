"""Giai doan 2 - test customer portal: quyền sở hữu, kiểm tra sân, không thu cọc."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from operations.models import Booking, Customer, FootballField, Invoice, Payment


class CustomerPortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        staff, _ = Group.objects.get_or_create(name='Staff')
        customer, _ = Group.objects.get_or_create(name='Customer')
        cls.u1 = users.objects.create_user(username='buyer1', password='some-test-password-99')
        cls.u1.groups.add(customer)
        cls.c1 = Customer.objects.create(user=cls.u1, name='Khach A', phone='0912345678')
        cls.u2 = users.objects.create_user(username='buyer2', password='some-test-password-99')
        cls.u2.groups.add(customer)
        cls.c2 = Customer.objects.create(user=cls.u2, name='Khach B', phone='0987654321')
        cls.employee = users.objects.create_user(username='worker', password='some-test-password-99')
        cls.employee.groups.add(staff)
        cls.field = FootballField.objects.create(name='Sân Demo', field_type=5, hourly_rate=200000)

    def setUp(self):
        self.tomorrow = timezone.localdate() + timedelta(days=1)

    def post(self, url, d=None):
        return self.client.post(url, data=json.dumps(d or {}), content_type='application/json')

    def book(self, start='17:00', end='18:30', day=None, field=None):
        return self.post('/api/customer/bookings/', {
            'fieldId': (field or self.field).pk,
            'date': (day or self.tomorrow).isoformat(),
            'start': start, 'end': end,
            'customerId': self.c2.pk,  # co tinh thu yeu cau doi danh tinh
            'price': 1, 'depositRate': 0,
        })

    def test_register_new_customer_without_promoting_role(self):
        response = self.post('/api/customer/register/', {
            'username': 'newcustomer', 'password': 'demo-safe-password-2026',
            'name': 'Khach hang C', 'phone': '0900123456',
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['role'], 'Customer')
        self.assertEqual(self.client.get('/api/session/').json()['role'], 'Customer')
        self.assertEqual(self.client.get('/api/state/').status_code, 403)
        profile = Customer.objects.get(phone='0900123456')
        self.assertEqual(profile.user.username, 'newcustomer')

    def test_registration_cannot_claim_old_profile_by_phone(self):
        response = self.post('/api/customer/register/', {
            'username':'newcustomer', 'password':'demo-safe-password-2026',
            'name':'Khach C', 'phone':self.c2.phone,
        })
        self.assertEqual(response.status_code, 409)
        self.assertFalse(get_user_model().objects.filter(username='newcustomer').exists())

    def test_customers_only_see_their_own_bookings(self):
        self.client.force_login(self.u1)
        made = self.book()
        self.assertEqual(made.status_code, 201, made.content)
        booking = Booking.objects.get(pk=made.json()['booking']['id'])
        self.assertEqual(booking.customer, self.c1)  # khong tin customerId tu client
        self.assertEqual(booking.created_by, self.u1)
        self.assertEqual(booking.deposit_percent, 40)
        self.assertEqual(booking.status, Booking.Status.BOOKED)
        self.assertEqual(Invoice.objects.get(booking=booking).status, Invoice.Status.DRAFT)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(self.client.get('/api/customer/bookings/').json()['items'][0]['id'],booking.pk)
        self.client.force_login(self.u2)
        self.assertEqual(self.client.get('/api/customer/bookings/').json()['items'],[])
        self.assertEqual(self.client.get('/api/state/').status_code,403)

    def test_conflict_is_rejected_and_availability_has_no_personal_data(self):
        self.client.force_login(self.u1)
        self.assertEqual(self.book().status_code,201)
        self.client.force_login(self.u2)
        check = self.client.get('/api/customer/availability/', {
            'date':self.tomorrow.isoformat(), 'fieldId':self.field.pk,
            'start':'17:30', 'end':'18:30',
        })
        self.assertEqual(check.status_code,200, check.content)
        self.assertFalse(check.json()['available'])
        self.assertNotIn(self.c1.name,check.content.decode('utf-8'))
        self.assertNotIn(self.c1.phone,check.content.decode('utf-8'))
        self.assertEqual(self.book('17:30','18:30').status_code,409)
        self.assertEqual(self.book('18:30','19:30').status_code,201)

    def test_customer_cannot_use_staff_api_or_fake_payment(self):
        self.client.force_login(self.u1)
        made = self.book()
        invoice_id = made.json()['booking']['invoiceId']
        self.assertEqual(self.post(f'/api/invoices/{invoice_id}/pay/', {
            'method':'bank','bankReference':'FAKE-12345','manuallyVerified':True,
        }).status_code,403)
        self.assertEqual(self.post(f'/api/invoices/{invoice_id}/deposit/', {
            'amount':100000,'method':'cash',
        }).status_code,403)
        self.assertEqual(Payment.objects.count(),0)

    def test_public_and_staff_cannot_use_customer_endpoints(self):
        self.assertEqual(self.client.get('/api/customer/bookings/').status_code,401)
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get('/api/customer/bookings/').status_code,403)
        self.assertEqual(self.client.get('/api/customer/fields/').status_code,403)
        self.assertEqual(self.client.get('/api/state/').status_code,200)
        self.assertRedirects(self.client.get('/khach/'), '/nhan-vien/', fetch_redirect_response=False)

    def test_invalid_slot_and_limit_three_bookings(self):
        self.client.force_login(self.u1)
        self.assertEqual(self.book('22:30','23:30').status_code,400)
        self.assertEqual(self.book('17:15','18:15').status_code,400)
        for offset in [1,2,3]:
            self.assertEqual(self.book(day=timezone.localdate()+timedelta(days=offset)).status_code,201)
        self.assertEqual(self.book(day=timezone.localdate()+timedelta(days=4)).status_code,409)

    def test_customer_portal_and_staff_portal_pages_are_available(self):
        self.assertRedirects(self.client.get('/khach/'), '/', fetch_redirect_response=False)
        self.assertContains(self.client.get('/'), 'Đăng nhập tài khoản')
        self.client.force_login(self.u1)
        self.assertContains(self.client.get('/khach/'), 'ĐẶT SÂN TRỰC TUYẾN')
        self.assertRedirects(self.client.get('/'), '/khach/', fetch_redirect_response=False)
