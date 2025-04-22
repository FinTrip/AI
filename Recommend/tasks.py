from datetime import  date
from django.core.mail import send_mail
from django.conf import settings
import MySQLdb
from celery import shared_task

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

        # Lấy các hoạt động chưa hoàn thành và đến hạn hôm nay
        cursor.execute(
            """
            SELECT a.activity_id, a.note_activities, a.date_activities, u.email
            FROM activities a
            JOIN users u ON a.user_id = u.id
            WHERE a.status = 0 AND a.date_activities = %s
            """,
            [today]
        )
        activities = cursor.fetchall()

        for activity in activities:
            activity_id, note_activities, date_activities, email = activity
            subject = 'Nhắc nhở hoạt động trong kế hoạch du lịch'
            message = (
                f"Xin chào {activity.user.get_full_name() or activity.user.username},\n\n"
                f"Bạn có một hoạt động chưa hoàn thành trong danh sách to-do:\n"
                f"- Hoạt động: {activity.note_activities}\n"
                f"- Ngày thực hiện: {activity.date_activities}\n\n"
                "Hãy kiểm tra và cập nhật trạng thái trong ứng dụng FinTrip nhé!\n\n"
                "Trân trọng,\n"
                "Đội ngũ FinTrip"
            )
            send_mail(subject, message, settings.EMAIL_HOST_USER, [email])

        cursor.close()
        db.close()

    except Exception as e:
        logger.error(f"Error in send_reminder_task: {str(e)}")

