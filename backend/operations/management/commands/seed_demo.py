"""Dữ liệu hư cấu được lưu trong SQLite cho bài tập MIS3047."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone
from operations.models import (
    Customer, FootballField, Product, Booking, Invoice, InvoiceLine, Payment,
    AuditLog, StockMovement
)


class Command(BaseCommand):
    help = 'Tạo tài khoản demo và dữ liệu nghiệp vụ có quan hệ nhất quán (idempotent).'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        managers, _ = Group.objects.get_or_create(name='Manager')
        staff_group, _ = Group.objects.get_or_create(name='Staff')
        customer_group, _ = Group.objects.get_or_create(name='Customer')
        staff, created = User.objects.get_or_create(username='nhanvien')
        if created:
            staff.set_password('PitchPro@2026')
            staff.first_name = 'Minh Anh'
            staff.last_name = 'Nguyễn'
            staff.save()
        staff.groups.add(staff_group)
        manager, created = User.objects.get_or_create(username='quanly')
        if created:
            manager.set_password('PitchPro@2026')
            manager.first_name = 'Quốc Bảo'
            manager.last_name = 'Trần'
            manager.is_staff = True
            manager.is_superuser = True  # Chỉ dùng cho demo cục bộ và Django Admin
            manager.save()
        manager.groups.add(managers)

        # Demo vai tro thu ba: tai khoan khach KHONG nhin duoc API noi bo.
        customer_user, created = User.objects.get_or_create(username='khachhang')
        if created:
            customer_user.set_password('PitchPro@2026')
            customer_user.first_name = 'Khách'
            customer_user.last_name = 'Demo'
            customer_user.save()
        customer_user.groups.add(customer_group)
        Customer.objects.get_or_create(
            user=customer_user,
            defaults={'name': 'Khách hàng Demo', 'phone': '0999099000'},
        )

        pitches = []
        for i in range(1, 9):
            kind = 5 if i <= 5 else 7
            p, _ = FootballField.objects.get_or_create(name=f'Sân {i:02d}', defaults={
                'field_type': kind, 'hourly_rate': 200000 if kind == 5 else 300000
            })
            pitches.append(p)
        for n, price, stock, unit, tracked in [
            ('Nước suối Aquafina 500ml', 10000, 160, 'chai', True),
            ('Nước tăng lực Red Bull', 18000, 110, 'lon', True),
            ('Trà xanh Không Độ', 12000, 85, 'chai', True),
            ('Băng quấn cổ chân', 25000, 42, 'cuộn', True),
            ('Thuê áo bib', 30000, 0, 'lượt', False),
            ('Thuê bóng thi đấu', 40000, 0, 'lượt', False),
        ]:
            Product.objects.get_or_create(name=n, defaults={
                'price': price, 'stock': stock, 'unit': unit, 'tracks_stock': tracked
            })

        today = timezone.localdate()
        yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)
        clubs = [
            'FC Sông Hàn', 'FC Hải Châu', 'FC Thanh Khê', 'FC An Hải',
            'FC Hòa Khánh', 'FC Cẩm Lệ', 'FC Bách Khoa', 'FC Mỹ Khê',
            'FC Hòa Xuân', 'FC Điện Bàn', 'FC Ngũ Hành Sơn', 'FC Sơn Trà',
        ]
        customers = []
        for i, name in enumerate(clubs):
            c, _ = Customer.objects.get_or_create(phone=f'090800{1100+i:04d}', defaults={'name': name})
            customers.append(c)

        def create(day, idx, field_index, a, b, status, method='cash', water=0):
            customer, field = customers[idx % len(customers)], pitches[field_index - 1]
            bk, made = Booking.objects.get_or_create(
                customer=customer, field=field, day=day, start_time=a,
                defaults={'end_time': b, 'status': status, 'created_by': staff}
            )
            if not made:
                return bk
            invoice = Invoice.objects.create(
                booking=bk, customer=customer, customer_name=customer.name,
                created_by=staff, status=('paid' if status == 'paid' else 'awaiting' if status == 'completed' else 'draft'),
                paid_at=timezone.now() if status == 'paid' else None,
                closed_at=timezone.now() if status in ('paid', 'completed') else None,
            )
            # Historical completed records: booking completed, invoice paid.
            if status == 'paid':
                bk.status = 'completed'
                bk.received_at = timezone.now() - timedelta(hours=2)
                bk.returned_at = timezone.now() - timedelta(minutes=20)
                bk.save(update_fields=['status', 'received_at', 'returned_at'])
            if status == 'completed':
                bk.returned_at = timezone.now()
                bk.save(update_fields=['returned_at'])
            duration = (b.hour*60+b.minute)-(a.hour*60+a.minute)
            rental = (Decimal(field.hourly_rate)*Decimal(duration)/Decimal(60)).quantize(Decimal('1'))
            InvoiceLine.objects.create(invoice=invoice, kind='rental',
                description=f'Thuê {field.name} {a:%H:%M}–{b:%H:%M}', quantity=1, unit_price=rental)
            if water:
                p = Product.objects.get(name='Nước suối Aquafina 500ml')
                line = InvoiceLine.objects.create(invoice=invoice, product=p, kind='product',
                    description=p.name, quantity=water, unit_price=p.price)
                p.stock = max(0, p.stock-water)
                p.save(update_fields=['stock'])
                StockMovement.objects.create(product=p, invoice_line=line, delta=-water, stock_after=p.stock, actor=staff)
            if status == 'paid':
                total = invoice.total
                Payment.objects.create(invoice=invoice, kind='settlement', method=method,
                    channel='manual', amount=total, status='success',
                    request_code=f'PT-{day:%Y%m%d}-{idx:03d}',
                    bank_reference=f'CK-{day:%Y%m%d}-{idx:03d}' if method == 'bank' else None,
                    business_day=day, created_by=staff, confirmed_by=staff,
                    confirmed_at=timezone.now())
            return bk

        # Hoạt động hôm qua: dữ liệu cho bảng hóa đơn và đối soát.
        for i, field_i, a, b, method, water in [
            (0,1,'07:00','08:30','cash',4),
            (1,3,'09:00','10:30','bank',3),
            (2,6,'16:00','17:30','cash',0),
            (3,7,'18:00','19:30','bank',6),
            (4,2,'19:30','21:00','cash',2),
            (5,8,'20:00','21:30','bank',0),
        ]:
            create(yesterday, i, field_i, time.fromisoformat(a), time.fromisoformat(b), 'paid', method, water)
        for i, field_i, a, b, method, water in [
            (6,1,'06:00','07:30','cash',2),
            (7,3,'08:00','09:30','bank',4),
            (8,6,'10:00','11:30','cash',6),
        ]:
            create(today, i, field_i, time.fromisoformat(a), time.fromisoformat(b), 'paid', method, water)

        # Có một hóa đơn trả sân chưa thanh toán để thao tác ngay.
        create(today, 9, 5, time(12,0), time(13,30), 'completed', water=3)

        # Có một sân đang dùng: khách gọi thêm nước rồi trả sân.
        minute = timezone.localtime().hour*60 + timezone.localtime().minute
        start_minute = max(1, min(minute-55, 22*60))
        end_minute = min(23*60+59, max(start_minute+90, minute+55))
        def t(m): return time(m//60, m%60)
        create(today, 10, 4, t(start_minute), t(end_minute), 'using')

        for i, fld, a, b in [
            (1,1,time(17,0),time(18,30)),
            (2,2,time(18,0),time(19,30)),
            (3,7,time(19,0),time(20,30)),
        ]:
            create(tomorrow, i, fld, a, b, 'booked')

        # Seed một kỳ QT02 đã khóa của hôm qua để minh họa lịch sử.
        from process_2.models import ReconciliationSession, BankStatement, BankStatementLine
        from process_2.services import ledger_totals, report_payload
        session, was_new = ReconciliationSession.objects.get_or_create(
            day=yesterday,
            defaults={
                'created_by': manager,
                'opening_cash': 0,
                'cash_transfer_out': 0,
                'counted_cash': 0,
                'status': 'locked',
                'locked_by': manager,
                'locked_at': timezone.now(),
                'approved_by': manager,
                'approved_at': timezone.now(),
                'notes': 'Kỳ demo đã đối chiếu và khóa sổ.',
            },
        )
        if was_new:
            totals = ledger_totals(yesterday)
            session.counted_cash = totals['cash']
            session.ledger_cash_snapshot = totals['cash']
            session.ledger_bank_snapshot = totals['bank']
            statement = BankStatement.objects.create(
                session=session,
                source_name='Sao kê demo đã đối chiếu',
                row_count=0,
                total_amount=0,
                imported_by=manager,
            )
            bank_payments = Payment.objects.filter(
                business_day=yesterday, status='success', method='bank'
            ).order_by('id')
            statement_rows = []
            for payment in bank_payments:
                statement_rows.append(BankStatementLine(
                    statement=statement,
                    transaction_ref=payment.bank_reference or payment.request_code,
                    amount=payment.amount,
                    description=f'Thanh toán hóa đơn #{payment.invoice_id}',
                ))
            BankStatementLine.objects.bulk_create(statement_rows)
            statement.row_count = len(statement_rows)
            statement.total_amount = totals['bank']
            statement.save(update_fields=['row_count', 'total_amount'])
            session.bank_statement_total = totals['bank']
            session.save()
            session.report_snapshot = report_payload(session)
            session.save(update_fields=['report_snapshot'])
        if not AuditLog.objects.filter(event='seed.complete').exists():
            AuditLog.objects.create(actor=staff, event='seed.complete', detail='Khởi tạo dữ liệu hư cấu phục vụ trình diễn MIS3047')
        self.stdout.write(self.style.SUCCESS('Đã chuẩn bị 8 sân, 6 sản phẩm và lịch sân/hóa đơn trong SQLite.'))
        self.stdout.write('Tài khoản demo: nhanvien, quanly, khachhang | mật khẩu: PitchPro@2026')
        self.stdout.write('Giai doan 1: khachhang CHUA co giao dien tu dat san; API noi bo tra ve 403.')
