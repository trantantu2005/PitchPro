"""Giai doan 2: mot cong dang nhap, dieu huong theo Customer/Staff/Manager."""
import json
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase


class UnifiedAuthRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.accounts = {}
        for role in ('Customer', 'Staff', 'Manager'):
            group, _ = Group.objects.get_or_create(name=role)
            user = get_user_model().objects.create_user(
                username='route_' + role.lower(), password='TestPassword123456!'
            )
            user.groups.add(group)
            cls.accounts[role] = user

    def test_guests_only_see_the_shared_login(self):
        for path in ('/', '/dang-nhap/', '/dang-ky/'):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, 'Đăng nhập tài khoản')
        for path in ('/khach/', '/nhan-vien/', '/quan-ly/'):
            with self.subTest(path=path):
                self.assertRedirects(self.client.get(path), '/', fetch_redirect_response=False)

    def test_login_returns_role_and_redirects_to_correct_page(self):
        expected = {'Customer': '/khach/', 'Staff': '/nhan-vien/', 'Manager': '/quan-ly/'}
        for role, home in expected.items():
            with self.subTest(role=role):
                self.client.logout()
                response = self.client.post(
                    '/api/session/',
                    data=json.dumps({'username': 'route_' + role.lower(), 'password': 'TestPassword123456!'}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['role'], role)
                self.assertRedirects(self.client.get('/'), home, fetch_redirect_response=False)
                self.assertEqual(self.client.get(home).status_code, 200)
                for other in expected.values():
                    if other != home:
                        self.assertRedirects(self.client.get(other), home, fetch_redirect_response=False)

    def test_customer_cannot_read_staff_page_or_internal_api(self):
        self.client.force_login(self.accounts['Customer'])
        self.assertRedirects(self.client.get('/nhan-vien/'), '/khach/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/quan-ly/'), '/khach/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/api/state/').status_code, 403)

    def test_logout_restores_login_gateway(self):
        self.client.force_login(self.accounts['Staff'])
        self.assertEqual(self.client.delete('/api/session/').status_code, 200)
        self.assertContains(self.client.get('/'), 'Đăng nhập tài khoản')

    def test_registration_page_only_creates_customer(self):
        self.assertContains(self.client.get('/dang-ky/'), 'Đăng ký khách hàng')
