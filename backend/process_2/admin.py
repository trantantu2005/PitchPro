from django.contrib import admin
from .models import (
    BankStatement, BankStatementLine, PendingItemResolution,
    ReconciliationException, ReconciliationReminder, ReconciliationSession,
)


class BankStatementLineInline(admin.TabularInline):
    model = BankStatementLine
    extra = 0
    readonly_fields = ('transaction_ref', 'amount', 'description')


@admin.register(ReconciliationSession)
class ReconciliationSessionAdmin(admin.ModelAdmin):
    list_display = ('day', 'status', 'ledger_cash_snapshot', 'ledger_bank_snapshot', 'created_by', 'approved_by', 'locked_at')
    list_filter = ('status', 'day')
    readonly_fields = ('created_at', 'updated_at', 'submitted_at', 'approved_at', 'locked_at', 'source_fingerprint')
    search_fields = ('day', 'notes')


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    list_display = ('session', 'source_name', 'row_count', 'total_amount', 'imported_at')
    inlines = [BankStatementLineInline]


@admin.register(ReconciliationException)
class ReconciliationExceptionAdmin(admin.ModelAdmin):
    list_display = ('code', 'session', 'category', 'status', 'created_at', 'reviewed_by')
    list_filter = ('category', 'status')
    search_fields = ('code', 'description', 'reason', 'evidence')


@admin.register(PendingItemResolution)
class PendingItemResolutionAdmin(admin.ModelAdmin):
    list_display = ('session', 'source_invoice_id', 'amount_due_at_cutoff', 'disposition', 'recorded_by')


@admin.register(ReconciliationReminder)
class ReconciliationReminderAdmin(admin.ModelAdmin):
    list_display = ('session', 'recipient', 'kind', 'due_at', 'submitted_at', 'created_at', 'read_at')
    list_filter = ('kind', 'created_at', 'read_at')
    search_fields = ('message', 'recipient__username')
    readonly_fields = ('created_at',)
