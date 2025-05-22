from datetime import date, datetime, timedelta
from django.core.mail import send_mail
from django.conf import settings
import MySQLdb
from celery import shared_task
import logging
import redis

logger = logging.getLogger(__name__)

MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'

# Kết nối tới Redis
redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)

@shared_task(bind=True, name="Recommend.tasks.send_activity_reminder_task")
def send_activity_reminder_task(self):
    logger.info("Bắt đầu send_activity_reminder_task")
    try:
        # Lấy thời gian hiện tại
        now = datetime.now()
        today = date.today()

        # Chỉ chạy trong khoảng 8:00 đến 8:05 sáng
        if not (now.hour == 8 and 0 <= now.minute <= 5):
            logger.info("Không phải 8:00-8:05 sáng, bỏ qua send_activity_reminder_task")
            return

        # Kiểm tra xem đã gửi email cho ngày hôm nay chưa
        last_sent_key = f"last_sent_activity_reminder:{today}"
        if redis_client.exists(last_sent_key):
            logger.info(f"Đã gửi email nhắc nhở hoạt động cho ngày {today}, bỏ qua.")
            return

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        # Lấy các hoạt động có date_activities là hôm nay và chưa hoàn thành
        cursor.execute(
            """
            SELECT a.activity_id, a.note_activities, a.date_activities, u.email, u.full_name
            FROM activities a
            JOIN users u ON a.user_id = u.id
            WHERE a.status = 0 AND a.date_activities = %s
            """,
            [today]
        )
        activities = cursor.fetchall()
        logger.info(f"Tìm thấy {len(activities)} hoạt động để nhắc nhở vào 8h sáng")

        for activity in activities:
            activity_id, note_activities, date_activities, email, full_name = activity
            reminder_key = f"activity_reminder:{activity_id}:{date_activities}"

            # Kiểm tra xem email đã được gửi chưa
            if redis_client.exists(reminder_key):
                logger.info(f"Email nhắc nhở hoạt động {activity_id} đã được gửi, bỏ qua.")
                continue

            logger.info(f"Gửi email nhắc nhở hoạt động tới {email} cho hoạt động {activity_id}")
            user_name = full_name if full_name else "Người dùng"
            subject = 'Nhắc nhở hoạt động trong kế hoạch du lịch'
            message = (
                f"Xin chào {user_name},\n\n"
                f"Hôm nay bạn có một hoạt động trong danh sách to-do:\n"
                f"- Hoạt động: {note_activities}\n"
                f"- Ngày thực hiện: {date_activities}\n\n"
                "Hãy kiểm tra và cập nhật trạng thái trong ứng dụng FinTrip nhé!\n\n"
                "Trân trọng,\n"
                "Đội ngũ FinTrip"
            )
            send_mail(subject, message, settings.EMAIL_HOST_USER, [email])
            logger.info(f"Đã gửi email nhắc nhở hoạt động tới {email}")

            # Đánh dấu email đã gửi
            redis_client.set(reminder_key, "sent")

        # Lưu thời gian gửi email cuối cùng cho ngày hôm nay
        redis_client.set(last_sent_key, "sent")

        cursor.close()
        db.close()

    except Exception as e:
        logger.error(f"Lỗi trong send_activity_reminder_task: {str(e)}")
        raise

@shared_task(bind=True, name="Recommend.tasks.send_trip_reminder_task")
def send_trip_reminder_task(self):
    logger.info("Bắt đầu send_trip_reminder_task")
    try:
        # Lấy thời gian hiện tại
        now = datetime.now()
        today = date.today()

        # Chỉ chạy trong khoảng 7:00 đến 7:05 sáng
        if not (now.hour == 7 and 0 <= now.minute <= 5):
            logger.info("Không phải 7:00-7:05 sáng, bỏ qua send_trip_reminder_task")
            return

        # Kiểm tra xem đã gửi email cho ngày hôm nay chưa
        last_sent_key = f"last_sent_trip_reminder:{today}"
        if redis_client.exists(last_sent_key):
            logger.info(f"Đã gửi email nhắc nhở chuyến đi cho ngày {today}, bỏ qua.")
            return

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        # Lấy tất cả hoạt động để kiểm tra date_plan
        cursor.execute(
            """
            SELECT a.activity_id, a.date_plan, u.email, u.full_name
            FROM activities a
            JOIN users u ON a.user_id = u.id
            WHERE a.status = 0
            """
        )
        activities = cursor.fetchall()
        logger.info(f"Tìm thấy {len(activities)} hoạt động để kiểm tra nhắc nhở chuyến đi")

        for activity in activities:
            activity_id, date_plan, email, full_name = activity
            user_name = full_name if full_name else "Người dùng"

            # Chuyển date_plan thành dạng date để so sánh
            if isinstance(date_plan, datetime):
                date_plan = date_plan.date()

            # Tính các ngày nhắc nhở
            days_until_trip = (date_plan - today).days
            reminder_types = {
                3: "trước 3 ngày",
                2: "trước 2 ngày",
                1: "trước 1 ngày",
                0: "ngày bắt đầu"
            }

            # Kiểm tra xem hôm nay có phải là ngày cần gửi nhắc nhở không
            for days, reminder_type in reminder_types.items():
                if days_until_trip == days:
                    reminder_key = f"trip_reminder:{activity_id}:{date_plan}:{days}"

                    # Kiểm tra xem email đã được gửi chưa
                    if redis_client.exists(reminder_key):
                        logger.info(f"Email nhắc nhở {reminder_type} cho chuyến đi {activity_id} đã được gửi, bỏ qua.")
                        continue

                    if days > 0:  # Nhắc nhở trước 3, 2, 1 ngày
                        logger.info(f"Gửi email nhắc nhở {reminder_type} tới {email} cho chuyến đi {activity_id}")
                        subject = f'Nhắc nhở: Còn {days} ngày nữa là đến chuyến đi của bạn!'
                        message = (
                            f"Xin chào {user_name},\n\n"
                            f"Chuyến đi của bạn sẽ bắt đầu vào ngày {date_plan}, còn {days} ngày nữa!\n"
                            f"Hãy chuẩn bị mọi thứ cần thiết để có một chuyến đi tuyệt vời nhé!\n\n"
                            "Trân trọng,\n"
                            "Đội ngũ FinTrip"
                        )
                    else:  # Ngày bắt đầu chuyến đi
                        logger.info(f"Gửi email chúc mừng tới {email} cho chuyến đi {activity_id}")
                        subject = 'Chúc bạn có một chuyến đi vui vẻ!'
                        message = (
                            f"Xin chào {user_name},\n\n"
                            f"Hôm nay là ngày bắt đầu chuyến đi của bạn ({date_plan})!\n"
                            f"Chúc bạn có một hành trình thật vui vẻ và đáng nhớ!\n\n"
                            "Trân trọng,\n"
                            "Đội ngũ FinTrip"
                        )

                    send_mail(subject, message, settings.EMAIL_HOST_USER, [email])
                    logger.info(f"Đã gửi email {reminder_type} tới {email}")

                    # Đánh dấu email đã gửi
                    redis_client.set(reminder_key, "sent")

        # Lưu thời gian gửi email cuối cùng cho ngày hôm nay
        redis_client.set(last_sent_key, "sent")

        cursor.close()
        db.close()

    except Exception as e:
        logger.error(f"Lỗi trong send_trip_reminder_task: {str(e)}")
        raise