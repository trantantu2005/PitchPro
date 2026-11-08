from django.urls import path
from . import views

app_name = 'process_2'
urlpatterns = [
    path('reconciliation/reminders/', views.reminders, name='reminders'),
    path('reconciliation/reminders/<int:reminder_id>/read/', views.reminder_read, name='reminder-read'),
    path('reconciliation/', views.reconciliation, name='reconciliation'),
    path('reconciliation/<str:day>/cash/', views.cash_count, name='cash-count'),
    path('reconciliation/<str:day>/bank-statement/', views.bank_statement_import, name='bank-statement-import'),
    path('reconciliation/<str:day>/detect/', views.detect, name='detect'),
    path('reconciliation/<str:day>/exceptions/<int:exception_id>/ai/', views.ai_analyze_exception, name='ai-exception'),
    path('reconciliation/<str:day>/exceptions/<int:exception_id>/evidence/', views.upload_exception_evidence, name='exception-evidence-upload'),
    path('reconciliation/<str:day>/pending/<int:invoice_id>/', views.pending_resolution, name='pending-resolution'),
    path('reconciliation/<str:day>/exceptions/<int:exception_id>/explain/', views.explain_exception, name='exception-explain'),
    path('reconciliation/<str:day>/exceptions/<int:exception_id>/decision/', views.decide_exception, name='exception-decision'),
    path('reconciliation/<str:day>/exceptions/<int:exception_id>/resolve/', views.resolve_exception, name='exception-resolve'),
    path('reconciliation/<str:day>/submit/', views.submit_reconciliation, name='submit'),
    path('reconciliation/<str:day>/<str:action>/', views.recon_action, name='action'),
    path('reconciliation/<str:day>/report.csv', views.report, name='report'),
]
