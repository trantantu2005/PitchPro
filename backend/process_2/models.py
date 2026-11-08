from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class ReconciliationSession(models.Model):
    """Một kỳ đối soát theo ngày kinh doanh; dữ liệu QT01 chỉ được đọc."""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Đang đối soát'
        SUBMITTED = 'submitted', 'Chờ quản lý duyệt'
        APPROVED = 'approved', 'Đã duyệt'
        LOCKED = 'locked', 'Đã khóa sổ'

    day = models.DateField(unique=True, db_index=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT, db_index=True)

    opening_cash = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True,
                                       validators=[MinValueValidator(0)])
    cash_transfer_out = models.DecimalField(max_digits=15, decimal_places=0, default=0,
                                            validators=[MinValueValidator(0)])
    counted_cash = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True,
                                       validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)

    ledger_cash_snapshot = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    ledger_bank_snapshot = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    bank_statement_total = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True)
    source_fingerprint = models.CharField(max_length=64, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='qt02_sessions_created')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name='qt02_sessions_submitted')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='qt02_sessions_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name='qt02_sessions_locked')
    locked_at = models.DateTimeField(null=True, blank=True)
    report_snapshot = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-day']
        indexes = [models.Index(fields=['status', 'day'])]

    def __str__(self):
        return f'Đối soát {self.day} ({self.status})'


class BankStatement(models.Model):
    """Thông tin lần nhập sao kê; dòng chi tiết nằm trong BankStatementLine."""
    session = models.OneToOneField(ReconciliationSession, on_delete=models.PROTECT,
                                   related_name='bank_statement')
    source_name = models.CharField(max_length=180)
    original_filename = models.CharField(max_length=180, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    imported_at = models.DateTimeField(default=timezone.now)


class BankStatementLine(models.Model):
    statement = models.ForeignKey(BankStatement, on_delete=models.PROTECT, related_name='lines')
    transaction_ref = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=15, decimal_places=0)
    description = models.CharField(max_length=250, blank=True)
    transaction_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['statement', 'transaction_ref'], name='qt02_unique_statement_ref')
        ]
        ordering = ['transaction_ref']


class ReconciliationException(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Chờ giải trình'
        REVIEW_PENDING = 'review_pending', 'Chờ quản lý duyệt'
        APPROVED = 'approved', 'Quản lý chấp nhận phương án'
        RESOLVED = 'resolved', 'Đã xử lý và khớp'
        REJECTED = 'rejected', 'Yêu cầu bổ sung'

    class Category(models.TextChoices):
        CASH_SHORTAGE = 'cash_shortage', 'Thiếu tiền mặt'
        CASH_OVERAGE = 'cash_overage', 'Thừa tiền mặt'
        BANK_MISSING = 'bank_missing', 'Thiếu giao dịch trên sao kê'
        BANK_EXTRA = 'bank_extra', 'Giao dịch thừa trên sao kê'
        BANK_MISMATCH = 'bank_mismatch', 'Sai số tiền giao dịch'
        BANK_REFERENCE_MISSING = 'bank_reference_missing', 'Thiếu mã tham chiếu ngân hàng'
        BANK_DATE_MISMATCH = 'bank_date_mismatch', 'Sai ngày giao dịch trên sao kê'
        PENDING_INVOICE = 'pending_invoice', 'Hóa đơn còn phải thu'
        OTHER = 'other', 'Khác'

    session = models.ForeignKey(ReconciliationSession, on_delete=models.PROTECT,
                                related_name='exceptions')
    code = models.CharField(max_length=80)
    category = models.CharField(max_length=30, choices=Category.choices)
    description = models.TextField()
    amount_difference = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    reason = models.TextField(blank=True)
    evidence = models.TextField(blank=True)
    proposed_action = models.TextField(blank=True)
    manager_feedback = models.TextField(blank=True)
    resolution = models.TextField(blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='qt02_exceptions_created')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name='qt02_exceptions_submitted')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='qt02_exceptions_reviewed')
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='qt02_exceptions_resolved')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'code'], name='qt02_unique_exception_code')
        ]
        ordering = ['status', 'created_at']

    def __str__(self):
        return f'{self.code} - {self.get_category_display()}'


class ReconciliationExceptionHistory(models.Model):
    """Lưu từng lần nhân viên gửi hồ sơ và từng quyết định của quản lý."""
    class Action(models.TextChoices):
        SUBMITTED = 'submitted', 'Nhân viên gửi giải trình'
        RESUBMITTED = 'resubmitted', 'Nhân viên bổ sung và gửi lại'
        SUPPLEMENT_REQUESTED = 'supplement_requested', 'Quản lý yêu cầu bổ sung'
        APPROVED = 'approved', 'Quản lý chấp nhận phương án'

    exception = models.ForeignKey(
        ReconciliationException,
        on_delete=models.PROTECT,
        related_name='history_entries',
    )
    revision_no = models.PositiveIntegerField()
    action = models.CharField(max_length=30, choices=Action.choices)
    status = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    evidence = models.TextField(blank=True)
    proposed_action = models.TextField(blank=True)
    manager_feedback = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='qt02_exception_history_actions',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['revision_no', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['exception', 'revision_no'],
                name='qt02_unique_exception_history_revision',
            )
        ]

    def __str__(self):
        return f'{self.exception.code} - lần {self.revision_no}'


class PendingItemResolution(models.Model):
    class Disposition(models.TextChoices):
        CARRY_FORWARD = 'carry_forward', 'Chuyển tiếp kỳ sau'
        SETTLED_LATER = 'settled_later', 'Đã tất toán sau ngày chốt'

    session = models.ForeignKey(ReconciliationSession, on_delete=models.PROTECT,
                                related_name='pending_resolutions')
    invoice = models.ForeignKey('operations.Invoice', null=True, blank=True,
                                on_delete=models.PROTECT, related_name='qt02_resolutions')
    source_invoice_id = models.PositiveIntegerField()
    amount_due_at_cutoff = models.DecimalField(max_digits=15, decimal_places=0)
    disposition = models.CharField(max_length=20, choices=Disposition.choices)
    note = models.TextField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'source_invoice_id'], name='qt02_unique_pending_invoice')
        ]
        ordering = ['source_invoice_id']


class ReconciliationReminder(models.Model):
    """Thông báo nội bộ cho Quản lý khi báo cáo chờ duyệt quá 10 phút."""
    session = models.ForeignKey(
        ReconciliationSession,
        on_delete=models.PROTECT,
        related_name='reminders',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='qt02_reminders',
    )
    kind = models.CharField(max_length=40, default='manager_approval_overdue')
    message = models.CharField(max_length=500)
    due_at = models.DateTimeField()
    submitted_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'recipient', 'kind', 'submitted_at'],
                name='qt02_unique_reminder_recipient_submission',
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'Nhắc duyệt QT02 {self.session.day} → {self.recipient}'

class ReconciliationAIAnalysis(models.Model):
    """Lưu vết gợi ý AI; không phải quyết định nghiệp vụ hay bút toán."""
    class AnalysisType(models.TextChoices):
        PENDING = 'pending', 'Phân tích khoản treo'
        EXCEPTION = 'exception', 'Phân tích ngoại lệ/chứng từ'

    session = models.ForeignKey(
        ReconciliationSession,
        on_delete=models.PROTECT,
        related_name='ai_analyses',
    )
    exception = models.ForeignKey(
        ReconciliationException,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='ai_analyses',
    )
    target_invoice_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    analysis_type = models.CharField(max_length=20, choices=AnalysisType.choices)
    provider = models.CharField(max_length=30, default='openai')
    model_name = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=30, default='qt02-a4-v1')
    source_fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='qt02_ai_analyses',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session', 'analysis_type', 'created_at']),
        ]

    def __str__(self):
        return f'AI {self.analysis_type} QT02 {self.session.day}'


class ReconciliationEvidenceDocument(models.Model):
    """Chứng từ đính kèm ngoại lệ; chỉ trích xuất văn bản PDF/TXT/CSV để AI đọc."""
    exception = models.ForeignKey(
        ReconciliationException,
        on_delete=models.PROTECT,
        related_name='evidence_documents',
    )
    file = models.FileField(upload_to='qt02_evidence/%Y/%m/%d/')
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    extracted_text = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='qt02_evidence_documents',
    )
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [models.Index(fields=['exception', 'uploaded_at'])]

    def __str__(self):
        return self.original_name

