from django.contrib import admin
from .models import (
    Customer, FootballField, Product, Booking, Invoice, InvoiceLine,
    Payment, StockMovement, AuditLog,
)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'user')
    search_fields = ('name', 'phone', 'user__username')

@admin.register(FootballField)
class FootballFieldAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'field_type', 'hourly_rate', 'is_active')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'stock', 'tracks_stock', 'is_active')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'field', 'customer', 'day', 'start_time', 'end_time', 'status')
    list_filter = ('day', 'status', 'field')
    search_fields = ('customer__name', 'customer__phone')
    readonly_fields = ('received_at', 'returned_at')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'customer', 'status', 'created_at', 'paid_at')
    list_filter = ('status',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'kind', 'method', 'amount', 'status', 'business_day')
    list_filter = ('status', 'method', 'business_day')
    readonly_fields = ('confirmed_at',)

admin.site.register(InvoiceLine)
admin.site.register(StockMovement)
admin.site.register(AuditLog)
# Model Reconciliation/ExceptionCase cũ được giữ lại để tương thích dữ liệu, không dùng trong QT02 mới.
admin.site.site_header = 'PitchPro - Quản lý sân bóng'
