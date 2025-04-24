from datetime import date
from django.core.mail import send_mail
from django.conf import settings
import MySQLdb
from celery import shared_task, current_app
import logging

logger = logging.getLogger(__name__)

MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'

@shared_task(bind=True, name="send_reminder_task")
def send_reminder_task():
    try:
        today = date.today()
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                            db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT a.activity_id, a.note_activities, a.date_activities, u.email, u.first_name, u.last_name
            FROM activities a
            JOIN users u ON a.user_id = u.id
            WHERE a.status = 0 AND a.date_activities = %s
            """,
            [today]
        )
        activities = cursor.fetchall()

        for activity in activities:
            activity_id, note_activities, date_activities, email, first_name, last_name = activity
            full_name = f"{first_name} {last_name}".strip() if first_name and last_name else (first_name or last_name or "Người dùng")
            subject = 'Nhắc nhở hoạt động trong kế hoạch du lịch'
            message = (
                f"Xin chào {full_name},\n\n"
                f"Bạn có một hoạt động chưa hoàn thành trong danh sách to-do:\n"
                f"- Hoạt động: {note_activities}\n"
                f"- Ngày thực hiện: {date_activities}\n\n"
                "Hãy kiểm tra và cập nhật trạng thái trong ứng dụng FinTrip nhé!\n\n"
                "Trân trọng,\n"
                "Đội ngũ FinTrip"
            )
            send_mail(subject, message, settings.EMAIL_HOST_USER, [email])

        cursor.close()
        db.close()

    except Exception as e:
        logger.error(f"Error in send_reminder_task: {str(e)}")

# Đăng ký thủ công tác vụ
current_app.tasks.register(send_reminder_task)