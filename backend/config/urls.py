"""PitchPro: mot cong dang nhap; dieu huong trang theo vai tro tai server.

/              : cong dang nhap chung (va dieu huong neu da dang nhap)
/dang-nhap/    : alias cho dang nhap
/dang-ky/      : dang ky khach hang (cung 1 giao dien)
/khach/        : chi Customer
/nhan-vien/    : chi Staff
/quan-ly/      : chi Manager
"""
from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.static import serve
from django.contrib import admin
from shared.api import role_of

ROLE_PATHS = {
    'Customer': '/khach/',
    'Staff': '/nhan-vien/',
    'Manager': '/quan-ly/',
}


def _correct_page(request):
    """Tai khoan sai nhom: quay ve trang cua ho, khong lo noi dung noi bo."""
    role = role_of(request.user)
    if role in ROLE_PATHS:
        return redirect(ROLE_PATHS[role])
    if request.user.is_authenticated:
        # Tai khoan khong co quyen hop le; chuyen ve cong xac thuc.
        logout(request)
    return redirect('/')


@never_cache
@ensure_csrf_cookie
def auth_gateway(request):
    """Cong xac thuc chung; user da dang nhap duoc chuyen tu dong."""
    if request.method != 'GET':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET'])
    role = role_of(request.user)
    if role in ROLE_PATHS:
        return redirect(ROLE_PATHS[role])
    if request.user.is_authenticated:
        logout(request)
    return render(request, 'auth.html')


@never_cache
def customer_page(request):
    if role_of(request.user) != 'Customer':
        return _correct_page(request)
    return render(request, 'customer.html')


@never_cache
def staff_page(request):
    if role_of(request.user) != 'Staff':
        return _correct_page(request)
    return render(request, 'index.html')


@never_cache
def manager_page(request):
    if role_of(request.user) != 'Manager':
        return _correct_page(request)
    return render(request, 'index.html')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/customer/', include('process_1.customer_urls')),
    path('api/', include('process_1.urls')),
    path('api/', include('process_2.urls')),
    path('', auth_gateway, name='auth-gateway'),
    path('dang-nhap/', auth_gateway, name='login'),
    path('dang-ky/', auth_gateway, name='customer-register-page'),
    path('khach/', customer_page, name='customer-page'),
    path('nhan-vien/', staff_page, name='staff-page'),
    path('quan-ly/', manager_page, name='manager-page'),
]

if settings.DEBUG:
    def private_media(request, path):
        """Chi nhan vien/quan ly doc chung tu QT02 o moi truong demo."""
        if role_of(request.user) not in ('Staff', 'Manager'):
            return HttpResponseForbidden('Khong co quyen xem chung tu.')
        return serve(request, path, document_root=settings.MEDIA_ROOT, show_indexes=False)

    urlpatterns += [re_path(r'^media/(?P<path>.*)$', private_media)]
