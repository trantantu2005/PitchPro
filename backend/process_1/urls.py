from django.urls import path
from . import views

app_name = 'process_1'
urlpatterns = [
    path('session/', views.session, name='session'),
    path('state/', views.state_snapshot, name='state'),
    path('bootstrap/', views.bootstrap, name='bootstrap'),
    path('bookings/', views.bookings, name='bookings'),
    path('bookings/<int:pk>/<str:action>/', views.booking_transition, name='booking-transition'),
    path('invoices/', views.invoices, name='invoices'),
    path('invoices/retail/', views.retail_sale, name='retail-sale'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice-detail'),
    path('invoices/<int:pk>/items/', views.invoice_add_item, name='invoice-add-item'),
    path('invoices/<int:pk>/finalize/', views.invoice_finalize, name='invoice-finalize'),
    path('invoices/<int:pk>/deposit/', views.deposit, name='deposit'),
    path('invoices/<int:pk>/qr/', views.qr_create, name='qr-create'),
    path('invoices/<int:pk>/qr/cancel/', views.qr_cancel, name='qr-cancel'),
    path('invoices/<int:pk>/qr/image/', views.qr_image, name='qr-image'),
    path('invoices/<int:pk>/pay/', views.pay, name='pay'),
    path('stock/restock/', views.stock_restock, name='stock-restock'),

]

# PitchPro - danh muc san pham
from django.urls import path as _pitchpro_path
from . import views as _pitchpro_views
urlpatterns += [_pitchpro_path('products/', _pitchpro_views.product_create, name='product-create')]
