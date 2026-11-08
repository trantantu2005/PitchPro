# Operations – Shared data layer

`operations/models.py` giữ các entity nguồn dùng chung:
- Customer, FootballField, Product, Booking.
- Invoice, InvoiceLine, Payment, StockMovement.
- AuditLog.

`Reconciliation` và `ExceptionCase` là model legacy từ bản đầu; QT02 mới không dùng hai model này.
Logic API QT01 nằm ở `process_1`; logic QT02 nằm ở `process_2`.
