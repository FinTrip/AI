from django.conf import settings
import jwt
import re
from datetime import datetime
from django.http import JsonResponse

MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'
PASSWORD_SECRET = getattr(settings, "PASSWORD_SECRET", settings.SECRET_KEY)

def validate_request(data, *required_fields):
    for field in required_fields:
        if not data.get(field, "").strip():
            return False, f"Thiếu trường bắt buộc: {field}"
    return True, None

def check_password(plain_password: str, jwt_hashed: str) -> bool:
    try:
        payload = jwt.decode(jwt_hashed, PASSWORD_SECRET, algorithms=["HS256"])
        return payload.get("password") == plain_password
    except jwt.InvalidTokenError:
        return False


def check_missing_fields(fields):
    missing = [key for key, value in fields.items() if not value]
    if missing:
        return JsonResponse({"error": f"Thiếu trường bắt buộc: {', '.join(missing)}"}, status=400)
    return None

def check_field_length(fields):
    if any(len(value) > 50 for value in fields.values()):
        return JsonResponse({"error": "Dữ liệu đầu vào không được dài quá 50 ký tự."}, status=400)
    return None

def check_province_format(province):
    province_pattern = r"^[A-Za-z\u00C0-\u1EF9\s]+$"
    if not re.match(province_pattern, province):
        return JsonResponse({"error": "Province chỉ được chứa chữ cái (kể cả có dấu) và khoảng trắng."}, status=400)
    return None

def check_date_format(date_str, field_name):
    date_pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(date_pattern, date_str):
        return JsonResponse({"error": f"Định dạng ngày không hợp lệ cho {field_name}. Vui lòng sử dụng YYYY-MM-DD."}, status=400)
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return JsonResponse({"error": f"Định dạng ngày không hợp lệ cho {field_name}. Vui lòng sử dụng YYYY-MM-DD."}, status=400)
    return None

def check_date_logic(start_date, end_date, current_date):
    if start_date < current_date or end_date < current_date:
        return JsonResponse({"error": "Ngày bắt đầu và ngày kết thúc phải không bé hơn ngày hiện tại."}, status=400)
    if start_date > end_date:
        return JsonResponse({"error": "Ngày bắt đầu phải bé hơn hoặc bằng ngày kết thúc."}, status=400)
    total_days = (end_date - start_date).days + 1
    if total_days > 30:
        return JsonResponse({"error": "Tổng số ngày của lịch trình không được vượt quá 30 ngày."}, status=400)
    return None