"""API cong khach hang - KHONG tron vao API noi bo cua Staff/Manager."""
from django.urls import path
from . import customer_views

urlpatterns = [
    path('register/', customer_views.register, name='customer-register'),
    path('fields/', customer_views.fields, name='customer-fields'),
    path('availability/', customer_views.availability, name='customer-availability'),
    path('bookings/', customer_views.bookings, name='customer-bookings'),
]
