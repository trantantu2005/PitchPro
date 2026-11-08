def invoice_json(inv):
    return {
        'id': inv.id,
        'bookingId': inv.booking_id,
        'customer': inv.customer_name or (inv.customer.name if inv.customer_id else 'Khách lẻ'),
        'status': inv.status,
        'total': int(inv.total),
        'collected': int(inv.collected),
        'due': int(inv.due),
        'items': [
            {'id': line.id, 'productId': line.product_id, 'name': line.description,
             'qty': line.quantity, 'unitPrice': int(line.unit_price)}
            for line in inv.lines.all()
        ],
        'receipts': [
            {'id': payment.id, 'type': payment.kind, 'method': payment.method,
             'status': payment.status,
             'amount': -abs(int(payment.amount)) if payment.kind == 'refund' else abs(int(payment.amount)),
             'reference': payment.bank_reference or payment.request_code,
             'createdAt': payment.created_at.isoformat()}
            for payment in inv.payments.all()
        ],
    }


def booking_json(booking):
    return {
        'id': booking.id,
        'pitchId': booking.field_id,
        'name': booking.customer.name,
        'phone': booking.customer.phone,
        'date': booking.day.isoformat(),
        'start': booking.start_time.strftime('%H:%M'),
        'end': booking.end_time.strftime('%H:%M'),
        'status': booking.status,
        'invoiceId': booking.invoice.id,
        'depositRate': booking.deposit_percent,
        'receivedAt': booking.received_at.isoformat() if booking.received_at else None,
        'returnedAt': booking.returned_at.isoformat() if booking.returned_at else None,
    }
