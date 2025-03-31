from django.conf import settings
import jwt

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
