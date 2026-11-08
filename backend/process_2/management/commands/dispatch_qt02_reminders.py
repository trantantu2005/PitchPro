from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from process_2.models import ReconciliationReminder, ReconciliationSession


class Command(BaseCommand):
    help = (
        'Tạo thông báo nội bộ cho Quản lý khi báo cáo QT02 đã trình '
        'nhưng chưa được xác nhận sau 10 phút.'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        due_before = now - timedelta(minutes=10)
        managers_group, _ = Group.objects.get_or_create(name='Manager')
        User = get_user_model()
        managers = User.objects.filter(
            Q(is_superuser=True) | Q(groups=managers_group),
            is_active=True,
        ).distinct()

        sessions = ReconciliationSession.objects.filter(
            status=ReconciliationSession.Status.SUBMITTED,
            submitted_at__isnull=False,
            submitted_at__lte=due_before,
        ).select_related('submitted_by').order_by('day')

        created_count = 0
        for session in sessions:
            due_at = session.submitted_at + timedelta(minutes=10)
            message = (
                f'Báo cáo đối soát ngày {session.day} đã được trình quá 10 phút '
                'và đang chờ Quản lý xác nhận.'
            )
            for manager in managers:
                _, created = ReconciliationReminder.objects.get_or_create(
                    session=session,
                    recipient=manager,
                    kind='manager_approval_overdue',
                    submitted_at=session.submitted_at,
                    defaults={
                        'message': message,
                        'due_at': due_at,
                        'submitted_at': session.submitted_at,
                    },
                )
                if created:
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Đã tạo {created_count} thông báo nhắc duyệt QT02.'
            )
        )
