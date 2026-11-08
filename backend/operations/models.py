from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, F
from django.utils import timezone

ZERO = Decimal('0')

class Customer(models.Model):
    # Tai khoan tu phuc vu: de NULL de khong anh huong khach duoc nhan vien tao tu truoc.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='customer_profile',
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, unique=True)

    def __str__(self): return f'{self.name} - {self.phone}'

class FootballField(models.Model):
    name = models.CharField(max_length=80, unique=True)
    field_type = models.PositiveSmallIntegerField(choices=[(5, 'Sân 5'), (7, 'Sân 7')])
    hourly_rate = models.DecimalField(max_digits=13, decimal_places=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)

    def __str__(self): return self.name

class Product(models.Model):
    name = models.CharField(max_length=150, unique=True)
    price = models.DecimalField(max_digits=13, decimal_places=0, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=30, default='cái')
    stock = models.PositiveIntegerField(default=0)
    tracks_stock = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self): return self.name

class Booking(models.Model):
    class Status(models.TextChoices):
        BOOKED = 'booked', 'Đã đặt'
        USING = 'using', 'Đang sử dụng'
        COMPLETED = 'completed', 'Đã trả sân'
        CANCELLED = 'cancelled', 'Đã hủy'

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='bookings')
    field = models.ForeignKey(FootballField, on_delete=models.PROTECT, related_name='bookings')
    day = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    received_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED, db_index=True)
    deposit_percent = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=['field', 'day', 'status'])]
        constraints = [models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='booking_end_after_start')]

class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Nháp'
        AWAITING = 'awaiting', 'Chờ thanh toán'
        QR_PENDING = 'qr_pending', 'Chờ QR'
        PAID = 'paid', 'Đã thanh toán'
        CANCELLED = 'cancelled', 'Đã hủy'

    booking = models.OneToOneField(Booking, null=True, blank=True, on_delete=models.PROTECT, related_name='invoice')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT)
    customer_name = models.CharField(max_length=150, default="")  # Snapshot khi lập hóa đơn
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    @property
    def total(self):
        return sum((line.quantity * line.unit_price for line in self.lines.all()), ZERO)

    @property
    def collected(self):
        # Khoản hoàn tiền được lưu âm về mặt dòng tiền, kể cả khi dữ liệu nguồn nhập số dương.
        return sum((
            (-abs(p.amount) if p.kind == 'refund' else abs(p.amount))
            for p in self.payments.filter(status='success')
        ), ZERO)

    @property
    def due(self):
        return max(ZERO, self.total - self.collected)

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=[('rental', 'Tiền sân'), ('product', 'Hàng hóa'), ('service', 'Dịch vụ')])
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=13, decimal_places=0, validators=[MinValueValidator(0)])

class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Đang chờ'
        SUCCESS = 'success', 'Đã nhận'
        CANCELLED = 'cancelled', 'Đã hủy'
    invoice = models.ForeignKey(Invoice, related_name='payments', on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=[('deposit', 'Tiền cọc'), ('settlement', 'Tất toán'), ('refund', 'Hoàn tiền')])
    method = models.CharField(max_length=10, choices=[('cash', 'Tiền mặt'), ('bank', 'Chuyển khoản')])
    channel = models.CharField(max_length=10, default='manual')
    amount = models.DecimalField(max_digits=13, decimal_places=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    request_code = models.CharField(max_length=80, unique=True)
    bank_reference = models.CharField(max_length=120, unique=True, null=True, blank=True)
    business_day = models.DateField(db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments_created')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='payments_confirmed')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

class StockMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    invoice_line = models.ForeignKey(InvoiceLine, null=True, blank=True, on_delete=models.PROTECT)
    delta = models.IntegerField()
    stock_after = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

class Reconciliation(models.Model):
    """LEGACY: schema đối soát cũ; QT02 mới dùng process_2.ReconciliationSession."""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Đang đối soát'
        APPROVED = 'approved', 'Đã duyệt'
        LOCKED = 'locked', 'Khóa sổ'
    day = models.DateField(unique=True)
    counted_cash = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True)
    counted_bank = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True)
    ledger_cash = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    ledger_bank = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reconciliations_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='reconciliations_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

class ExceptionCase(models.Model):
    """LEGACY: ngoại lệ đối soát cũ; QT02 mới dùng process_2.ReconciliationException."""
    reconciliation = models.ForeignKey(Reconciliation, on_delete=models.PROTECT, related_name='exceptions')
    description = models.TextField()
    status = models.CharField(max_length=15, choices=[('pending', 'Cần xử lý'), ('resolved', 'Đã giải quyết')], default='pending')
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event = models.CharField(max_length=80)
    detail = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
