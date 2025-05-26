import json
import os
import re
from django.core.cache import cache

import pandas as pd
import uuid
import traceback
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
import MySQLdb
import logging
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
import jwt
from dotenv import load_dotenv

from .CheckException import validate_request, check_missing_fields, check_field_length, check_province_format, check_date_format, check_date_logic
from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv, update_hotel_in_csv, delete_hotel_in_csv, show_hotel_in_csv, get_hotel_homepage
from .processed import load_data, recommend_schedule, FOOD_FILE, PLACE_FILE, HOTEL_FILE, normalize_text, \
    get_food_homepage, get_place_homepage, get_city_to_be_miss,place_exists,food_exists
from .weather import display_forecast, get_weather
import redis

redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

# Thiết lập logging
logger = logging.getLogger(__name__)

load_dotenv()

# Cấu hình MySQL từ settings.py
MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'

air_province = ["quảng nam", "thanh hoá", "quảng bình", "điện biên", "phú yên", "gia lai", "khánh hoà", "huế", "cần thơ",
                "đắk lắk", "kiên giang", "cà mau", "vũng tàu", "hà nội", "hồ chí minh", "kiên giang", "đà nẵng", "quảng ninh",
                "nghệ an", "bình định", "hải phòng", "lâm đồng", "đồng nai"]

# Kiểm tra PASSWORD_SECRET
PASSWORD_SECRET = os.getenv("PASSWORD_SECRET")
if not PASSWORD_SECRET:
    raise ValueError("PASSWORD_SECRET environment variable is not set.")

# Hàm mã hóa mật khẩu bằng JWT (giữ nguyên để tương thích với dữ liệu hiện tại)
def hash_password(plain_password: str) -> str:
    payload = {"password": plain_password}
    return jwt.encode(payload, PASSWORD_SECRET, algorithm="HS256")

# Hàm kiểm tra mật khẩu
def check_password(plain_password: str, jwt_hashed: str) -> bool:
    try:
        payload = jwt.decode(jwt_hashed, PASSWORD_SECRET, algorithms=["HS256"])
        return payload.get("password") == plain_password
    except jwt.InvalidTokenError:
        return False

# Hàm đăng nhập người dùng
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def login_user(request):
    logger.debug(f"Request method: {request.method}")
    if request.method == 'GET':
        if request.user.is_authenticated:
            return JsonResponse({"message": "Người dùng đã đăng nhập", "user_id": request.user.id}, status=200)
        return JsonResponse({"message": "Vui lòng sử dụng phương thức POST để đăng nhập"}, status=200)
    elif request.method == 'POST':
        try:
            logger.debug(f"Raw request body: {request.body}")
            data = json.loads(request.body)
            logger.debug(f"Parsed JSON: {data}")

            # Kiểm tra dữ liệu đầu vào
            is_valid, error_message = validate_request(data, 'email', 'password')
            if not is_valid:
                logger.debug(f"Validation error: {error_message}")
                return JsonResponse({"error": error_message}, status=400)

            email = data.get("email", "").strip()
            password = data.get("password", "").strip()
            logger.debug(f"Attempting login for email: {email}, password: {'*' * len(password) if password else 'empty'}")

            # Kết nối MySQL
            db = MySQLdb.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                passwd=MYSQL_PASSWORD,
                db=MYSQL_DB,
                port=MYSQL_PORT,
                charset=MYSQL_CHARSET
            )
            cursor = db.cursor()
            logger.debug("Database connected")
            cursor.execute("SELECT id, password FROM users WHERE email = %s", [email])
            user = cursor.fetchone()
            logger.debug(f"Database query result: {user}")

            if not user:
                logger.debug("No user found with email")
                cursor.close()
                db.close()
                return JsonResponse({"error": "Email không tồn tại"}, status=400)

            # Kiểm tra mật khẩu
            user_id, hashed_password = user
            if not check_password(password, hashed_password):
                logger.debug(f"Password check failed. Input: {password}, Hashed: {hashed_password}")
                cursor.close()
                db.close()
                return JsonResponse({"error": "Mật khẩu không đúng"}, status=400)

            cursor.close()
            db.close()
            logger.debug(f"User found with ID: {user_id}")

            # Tạo JWT token
            payload = dict(user_id=user_id, email=email, exp=datetime.datetime.utcnow() + datetime.timedelta(hours=24))
            token = jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm=os.getenv("JWT_ALGORITHM"))

            # Kiểm tra hoặc tạo người dùng trong auth_user
            try:
                django_user = User.objects.get(username=email)
                if django_user.id != user_id:
                    logger.error(f"User ID mismatch: auth_user.id={django_user.id}, Users.id={user_id}")
                    return JsonResponse({"error": "Lỗi đồng bộ người dùng, vui lòng liên hệ quản trị viên"}, status=500)
            except User.DoesNotExist:
                logger.debug(f"Creating new Django user for email: {email}")
                django_user = User.objects.create_user(id=user_id, username=email, email=email, password=password)

            login(request, django_user)
            request.session['user_id'] = user_id
            logger.debug(f"User logged in: {django_user.username}, Django User ID: {django_user.id}, Custom User ID: {user_id}")
            return JsonResponse({
                "message": "Đăng nhập thành công",
                "user_id": user_id,
                "token": token
            }, status=200)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
        except MySQLdb.Error as e:
            logger.error(f"Database error: {str(e)}", exc_info=True)
            return JsonResponse({"error": f"Lỗi cơ sở dữ liệu: {str(e)}"}, status=500)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return JsonResponse({"error": f"Lỗi không xác định: {str(e)}"}, status=500)

@csrf_exempt
@require_http_methods(['POST'])
def verify_token(request):
    try:
        data = json.loads(request.body)
        token = data.get("token", "").strip()

        if not token:
            return JsonResponse({"error": "Thiếu token"}, status=400)

        # Giải mã token
        payload = jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=[os.getenv("JWT_ALGORITHM")])
        email = payload.get("email")
        if not email:
            return JsonResponse({"error": "Token không hợp lệ"}, status=400)

        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", [email])
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if not user:
            return JsonResponse({"error": "Người dùng không tồn tại"}, status=400)

        user_id = user[0]

        # Trả về phản hồi thành công
        return JsonResponse({"message": "Xác thực token thành công", "user_id": user_id}, status=200)

    except jwt.ExpiredSignatureError:
        return JsonResponse({"error": "Token đã hết hạn"}, status=401)
    except jwt.InvalidTokenError:
        return JsonResponse({"error": "Token không hợp lệ"}, status=401)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except MySQLdb.Error as e:
        return JsonResponse({"error": f"Lỗi cơ sở dữ liệu: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Lỗi không xác định: {str(e)}"}, status=500)



# Hàm đăng xuất người dùng
@csrf_exempt
@require_POST
def logout_user(request):
    try:
        logout(request)
        logger.debug("User logged out successfully")
        return JsonResponse({"message": "Đăng xuất thành công"}, status=200)
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

# API gợi ý lịch trình 1 ngày
@csrf_exempt
@require_POST
def recommend_travel_day(request):
    try:
        data = json.loads(request.body)
        location = data.get("location", "").strip()
        if not location:
            return JsonResponse({"error": "Thiếu trường bắt buộc: location"}, status=400)

        if len(location) > 100:
            return JsonResponse({"error": "Location không được dài quá 100 ký tự."}, status=400)

        food_df, place_df, _ = load_data(FOOD_FILE, PLACE_FILE)
        recommendations = recommend_schedule(location, food_df, place_df)
        if not recommendations:
            return JsonResponse({"error": "Không tìm thấy gợi ý cho địa điểm này."}, status=404)

        return JsonResponse({
            "recommendations": recommendations,
            "location": location,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in recommend_travel_day: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)



'''


bắt đầu q&a để đưa ra lịch trình 


'''


# Hàm xóa toàn bộ cache liên quan đến session
def clear_session_cache(session_key):
    cache_keys = [
        f'selected_province_{session_key}',
        f'start_day_{session_key}',
        f'end_day_{session_key}',
        f'budget_{session_key}',
        f'selected_flight_{session_key}',
        f'selected_hotel_{session_key}',
    ]
    for key in cache_keys:
        cache.delete(key)


# Endpoint để bắt đầu khảo sát mới
@require_GET
def start_survey(request):
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    clear_session_cache(session_key)
    return JsonResponse({"message": "Bắt đầu khảo sát mới, dữ liệu cũ đã được xóa."}, status=200)

@csrf_exempt
@require_POST
def set_province(request):
    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()

        fields = {"province": province}
        error_response = check_missing_fields(fields)
        if error_response:
            return error_response

        error_response = check_field_length(fields)
        if error_response:
            return error_response

        error_response = check_province_format(province)
        if error_response:
            return error_response

        cache_key = f'selected_province_{request.session.session_key}'
        cache.set(cache_key, province, timeout=3600)
        logger.info(f"Province saved to cache: {province}")
        return JsonResponse({"message": "Tỉnh đã được lưu."}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in set_province")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)

@csrf_exempt
@require_POST
def set_dates(request):
    try:
        data = json.loads(request.body)
        start_day = data.get("start_day", "").strip()
        end_day = data.get("end_day", "").strip()

        fields = {"start_day": start_day, "end_day": end_day}
        error_response = check_missing_fields(fields)
        if error_response:
            return error_response

        error_response = check_field_length(fields)
        if error_response:
            return error_response

        error = check_date_format(start_day, "start_day") or check_date_format(end_day, "end_day")
        if error:
            return error

        fmt = "%Y-%m-%d"
        start_date = datetime.strptime(start_day, fmt).date()
        end_date = datetime.strptime(end_day, fmt).date()
        current_date = datetime.now().date()

        error_response = check_date_logic(start_date, end_date, current_date)
        if error_response:
            return error_response

        cache_key_prefix = request.session.session_key
        cache.set(f'start_day_{cache_key_prefix}', start_day, timeout=3600)
        cache.set(f'end_day_{cache_key_prefix}', end_day, timeout=3600)
        logger.info(f"Dates saved to cache: start_day={start_day}, end_day={end_day}")
        return JsonResponse({"message": "Ngày đã được lưu."}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in set_dates")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)

@require_GET
def check_flight_di(request):
    data = json.loads(request.body)
    selected_province = data.get("departureInput", "").strip()

    if not selected_province:
        return JsonResponse({
            "error": "Bạn chưa chọn tỉnh/thành phố. Vui lòng chọn để tiếp tục."
        }, status=400)
    has_airport = selected_province in [province.lower() for province in air_province]

    if not has_airport:
        message = f"'{selected_province.title()}' hiện tại tỉnh của bạn chưa có sân bay. Vui lòng chọn dịch vụ khách sạn phù hợp."

    return JsonResponse({
        "has_airport": has_airport,
        "message": message
    }, status=200)

@require_GET
def check_flight_den(request):
    session_key = request.session.session_key
    selected_province = cache.get(f'selected_province_{session_key}', '').strip().lower()

    if not selected_province:
        return JsonResponse({
            "error": "Bạn chưa chọn tỉnh/thành phố. Vui lòng chọn để tiếp tục."
        }, status=400)
    has_airport = selected_province in [province.lower() for province in air_province]

    if not has_airport:
        message = f"'{selected_province.title()}' hiện chưa có sân bay. Vui lòng chọn dịch vụ khách sạn phù hợp."

    return JsonResponse({
        "has_airport": has_airport,
        "message": message
    }, status=200)

# API tìm kiếm chuyến bay
@csrf_exempt
@require_POST
def rcm_flight(request):
    try:
        data = json.loads(request.body)
        cache_key_prefix = request.session.session_key
        origin = data.get("origin", "").strip()
        destination = data.get("destination", cache.get(f'selected_province_{cache_key_prefix}', '')).strip()
        departure_date = data.get("departure_date", cache.get(f'start_day_{cache_key_prefix}', '')).strip()

        if not origin or not destination or not departure_date:
            return JsonResponse({"error": "Thiếu trường bắt buộc: origin, destination, departure_date"}, status=400)

        if any(len(value) > 50 for value in [origin, destination, departure_date]):
            return JsonResponse({"error": "Dữ liệu đầu vào quá dài."}, status=400)

        if any(char in origin + destination for char in "<>\"'{}[]()|&;"):
            return JsonResponse({"error": "Dữ liệu chứa ký tự không hợp lệ."}, status=400)

        result = search_flight_service(origin, destination, departure_date)
        if "error" in result:
            return JsonResponse({"error": result["error"]}, status=400)

        return JsonResponse(result, safe=False, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in rcm_flight")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        logger.error(f"Error in rcm_flight: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API lưu thông tin chuyến bay
@csrf_exempt
@require_POST
def select_flight(request):
    try:
        data = json.loads(request.body)
        flight_info = data.get('flight_info')
        if not flight_info:
            logger.error("Missing flight_info in select_flight")
            return JsonResponse({"error": "Missing flight info"}, status=400)

        cache_key = f'selected_flight_{request.session.session_key}'
        cache.set(cache_key, flight_info, timeout=3600)
        logger.info(f"Flight saved to cache: {flight_info}")
        return JsonResponse({"message": "Flight selected successfully"}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in select_flight")
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error in select_flight: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": f"Error system: {str(e)}"}, status=400)

# API tìm kiếm khách sạn
@csrf_exempt
@require_POST
def rcm_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        cache_key_prefix = request.session.session_key
        search_term = data.get("destination", cache.get(f'selected_province_{cache_key_prefix}', '')).strip()

        if not search_term:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        if len(search_term) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        result = process_hotel_data_from_csv(search_term)
        if not result:
            return JsonResponse({"error": "Không tìm thấy khách sạn."}, status=404)

        return JsonResponse({
            "hotels": result,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in rcm_hotel")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        logger.error(f"Error in rcm_hotel: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

# API lưu khách sạn đã chọn
@csrf_exempt
@require_POST
def select_hotel(request):
    try:
        data = json.loads(request.body)
        hotel_info = data.get('hotel_info')
        if not hotel_info:
            logger.error("Missing hotel_info in select_hotel")
            return JsonResponse({"error": "Missing hotel info"}, status=400)

        cache_key = f'selected_hotel_{request.session.session_key}'
        cache.set(cache_key, hotel_info, timeout=3600)
        logger.info(f"Hotel saved to cache: {hotel_info}")
        return JsonResponse({"message": "Hotel selected successfully"}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in select_hotel")
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error in select_hotel: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

# API tạo lịch trình
@csrf_exempt
@require_POST
def recommend_travel_schedule(request):
    try:
        data = json.loads(request.body)
        cache_key_prefix = request.session.session_key
        province = data.get('province', cache.get(f'selected_province_{cache_key_prefix}', ''))
        start_day = data.get('start_day', cache.get(f'start_day_{cache_key_prefix}', ''))
        end_day = data.get('end_day', cache.get(f'end_day_{cache_key_prefix}', ''))
        flight_info = data.get('flight_info', None)
        hotel_info = data.get('hotel_info', None)

        if not province or not start_day or not end_day:
            logger.error("Missing required fields in travel_schedule")
            return JsonResponse({"error": "Thiếu thông tin tỉnh, ngày đi hoặc ngày về"}, status=400)

        if flight_info:
            cache.set(f'selected_flight_{cache_key_prefix}', flight_info, timeout=3600)
            logger.info(f"Flight info updated in cache: {flight_info}")
        if hotel_info:
            cache.set(f'selected_hotel_{cache_key_prefix}', hotel_info, timeout=3600)
            logger.info(f"Hotel info updated in cache: {hotel_info}")

        selected_hotel = cache.get(f'selected_hotel_{cache_key_prefix}', {})
        selected_flight = cache.get(f'selected_flight_{cache_key_prefix}', {})

        if not selected_flight:
            logger.warning("No flight information found in cache")
        if not selected_hotel:
            logger.warning("No hotel information found in cache")

        start_date = datetime.strptime(start_day, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_day, "%Y-%m-%d").date()
        current_date = datetime.now().date()
        error_response = check_date_logic(start_date, end_date, current_date)
        if error_response:
            return error_response

        food_df, place_df, _ = load_data(FOOD_FILE, PLACE_FILE)
        schedule_result = recommend_schedule(start_day, end_day, province, food_df, place_df)
        if "error" in schedule_result:
            return JsonResponse({"error": schedule_result["error"]}, status=400)

        response_data = {
            "schedule": schedule_result,
            "hotel": selected_hotel,
            "flight": selected_flight,
            "province": province,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request),
        }

        logger.info("Travel schedule generated successfully")
        return JsonResponse(response_data, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in travel_schedule")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
    except Exception as e:
        logger.error(f"Error in travel_schedule: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)



'''

Kết thúc lịch trinh

'''


'''
Save share view
'''
def extract_hotel_class(hotel_class_raw):
    if hotel_class_raw is None:
        return None
    if isinstance(hotel_class_raw, (int, float)):
        return int(hotel_class_raw)
    elif isinstance(hotel_class_raw, str):
        match = re.search(r'\d+', hotel_class_raw)
        if match:
            return int(match.group())
        else:
            return None  # Hoặc có thể trả về giá trị mặc định như 0 nếu cột không cho phép NULL
    else:
        return None


# API lưu lịch trình
@csrf_exempt
@require_POST
def save_schedule(request):
    db = None
    cursor = None
    try:
        # **Parse JSON từ request**
        data = json.loads(request.body)
        user_id = data.get("user_id")
        if not user_id:
            logger.error("Thiếu user_id trong request")
            return JsonResponse({"error": "Thiếu user_id"}, status=400)

        # **Kết nối database**
        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()
        logger.info(f"Kết nối database thành công cho user_id: {user_id}")

        # **Kiểm tra user_id có tồn tại không**
        cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
        if not cursor.fetchone():
            logger.error(f"Không tìm thấy user với id: {user_id}")
            return JsonResponse({"error": "Không tìm thấy người dùng"}, status=404)

        # **Lấy dữ liệu từ request**
        schedule_name = data.get("schedule_name", "Lịch trình của tôi").strip()
        days_data = data.get("days", [])
        hotel_data = data.get("hotel", {})

        if not days_data or not isinstance(days_data, list):
            logger.error("Danh sách ngày rỗng hoặc không hợp lệ")
            return JsonResponse({"error": "Danh sách ngày rỗng hoặc không hợp lệ"}, status=400)

        # **Chèn dữ liệu vào bảng schedules**
        now = datetime.now()
        cursor.execute("INSERT INTO schedules (user_id, name, created_at) VALUES (%s, %s, %s)",
                       [user_id, schedule_name, now])
        schedule_id = cursor.lastrowid
        logger.info(f"Đã chèn schedule với id: {schedule_id}")

        # **Chèn dữ liệu vào bảng hotels**
        if hotel_data and isinstance(hotel_data, dict):
            name = hotel_data.get("name", "").strip()
            if name:
                # Xử lý price
                price_str = hotel_data.get("price", "")
                price = None
                if price_str:
                    try:
                        price = float(price_str.replace(",", ""))
                    except ValueError:
                        logger.warning(f"Price không hợp lệ: {price_str}")

                # Xử lý location_rating
                location_rating_str = hotel_data.get("location_rating", "")
                location_rating = None
                if location_rating_str:
                    try:
                        location_rating = float(location_rating_str)
                    except ValueError:
                        logger.warning(f"Location_rating không hợp lệ: {location_rating_str}")
                else:
                    location_rating = 3

                # Xử lý hotel_class
                hotel_class_raw = hotel_data.get("hotel_class")
                hotel_class = extract_hotel_class(hotel_class_raw) if hotel_class_raw else None

                # Chèn dữ liệu với đúng 9 tham số
                cursor.execute(
                    """
                    INSERT INTO hotels (schedule_id, name, address, description, price, hotel_class,
                                       img_origin, location_rating, link,created_at,updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        schedule_id,
                        name,
                        "",  # Address không có trong hotel_data, dùng chuỗi rỗng
                        hotel_data.get("description", ""),
                        price,
                        hotel_class,
                        hotel_data.get("img_origin", ""),
                        location_rating,
                        hotel_data.get("link", ""),
                        now,now
                    ]
                )
                logger.info(f"Đã chèn hotel cho schedule_id: {schedule_id}")
            else:
                logger.warning("Thiếu tên khách sạn, không chèn hotel")

        # **Chèn dữ liệu vào bảng days và itineraries**
        for day in days_data:
            date_str = day.get("date_str", "").strip()
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"date_str không được cung cấp, sử dụng ngày hiện tại: {date_str}")
            else:
                try:
                    parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    date_str = parsed_date.strftime("%Y-%m-%d")
                except ValueError:
                    logger.error(f"Định dạng date_str không hợp lệ: {date_str}")
                    return JsonResponse({"error": f"Định dạng date_str không hợp lệ: {date_str}"}, status=400)

            cursor.execute(
                "INSERT INTO days (schedule_id, day_index, date_str) VALUES (%s, %s, %s)",
                [schedule_id, day.get("day_index", 0), date_str]
            )
            day_id = cursor.lastrowid
            logger.info(f"Đã chèn day với id: {day_id}")

            for item in day.get("itinerary", []):
                if not isinstance(item, dict):
                    logger.warning(f"Item không phải dict: {item}")
                    continue
                food_title = item.get("food_title", "").strip()
                place_title = item.get("place_title", "").strip()
                if not food_title and not place_title:
                    logger.info("Bỏ qua item vì thiếu cả food_title và place_title")
                    continue

                food_rating = item.get("food_rating")
                if food_rating:
                    try:
                        food_rating = float(food_rating)
                    except (ValueError, TypeError):
                        food_rating = None

                place_rating = item.get("place_rating")
                if place_rating:
                    try:
                        place_rating = float(place_rating)
                    except (ValueError, TypeError):
                        place_rating = None

                cursor.execute(
                    """
                    INSERT INTO itineraries (
                        day_id, timeslot, food_title, food_rating, food_price, food_address,
                        food_phone, food_link, food_image, food_time, place_title, place_rating,
                        place_description, place_address, place_img, place_link, place_time,
                        `order`, schedule_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        day_id,
                        item.get("timeslot", "")[:20],
                        food_title[:100],
                        food_rating,
                        str(item.get("food_price", ""))[:50],
                        item.get("food_address", "")[:200],
                        item.get("food_phone", "")[:20],
                        item.get("food_link", "")[:255],
                        item.get("food_image", "")[:255],
                        item.get("food_time", "")[:255] if item.get("food_time") else None,
                        place_title[:100],
                        place_rating,
                        item.get("place_description", ""),
                        item.get("place_address", "")[:200],
                        item.get("place_img", "")[:255],
                        item.get("place_link", "")[:255],
                        item.get("place_time", "")[:255] if item.get("place_time") else None,
                        item.get("order", 0),
                        schedule_id
                    ]
                )
                logger.info(f"Đã chèn itinerary cho day_id: {day_id}")

        # **Chèn dữ liệu vào bảng sharedlinks**
        share_token = str(uuid.uuid4()).lower()
        share_link = f"{request.scheme}://{request.get_host()}/recommend/view-schedule/{share_token}/"
        cursor.execute(
            "INSERT INTO sharedlinks (schedule_id, share_link, created_at) VALUES (%s, %s, NOW())",
            [schedule_id, share_link]
        )
        logger.info(f"Đã chèn sharedlink cho schedule_id: {schedule_id}")

        # **Commit tất cả thay đổi**
        db.commit()
        logger.info("Đã commit tất cả thay đổi thành công")

        return JsonResponse({
            "message": "Lịch trình lưu thành công",
            "schedule_id": schedule_id,
            "share_link": share_link
        }, status=201)

    except json.JSONDecodeError:
        logger.error("JSON không hợp lệ trong request")
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except MySQLdb.Error as e:
        if db:
            db.rollback()
        logger.error(f"Lỗi database: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"Lỗi không xác định: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi server"}, status=500)
    finally:
        if cursor:
            cursor.close()
        if db and db.open:
            db.close()
            logger.info("Đã đóng kết nối database")



@csrf_exempt
@require_POST
def share_schedule(request):
    db = None
    cursor = None
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        schedule_id = data.get("schedule_id")

        if not user_id:
            return JsonResponse({"error": "Thiếu user_id"}, status=400)
        if not schedule_id:
            return JsonResponse({"error": "Thiếu schedule_id"}, status=400)

        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()

        # Kiểm tra quyền chia sẻ
        cursor.execute("SELECT user_id FROM schedules WHERE id = %s", [schedule_id])
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return JsonResponse({"error": "Không có quyền chia sẻ"}, status=403)

        # Kiểm tra liên kết chia sẻ đã tồn tại chưa
        cursor.execute("SELECT share_link FROM sharedlinks WHERE schedule_id = %s", [schedule_id])
        existing_link = cursor.fetchone()
        if existing_link:
            return JsonResponse({"message": "Liên kết đã tồn tại", "share_link": existing_link[0]}, status=200)

        # Tạo và chèn liên kết chia sẻ mới
        share_token = str(uuid.uuid4()).lower()
        share_link = f"http://{request.get_host()}/recommend/view-schedule/{share_token}/"
        cursor.execute(
            "INSERT INTO sharedlinks (schedule_id, share_link) VALUES (%s, %s)",
            [schedule_id, share_link]
        )
        db.commit()

        return JsonResponse({"message": "Chia sẻ thành công", "share_link": share_link}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except MySQLdb.IntegrityError:
        return JsonResponse({"error": "Liên kết chia sẻ đã tồn tại"}, status=409)
    except MySQLdb.Error:
        if db:
            db.rollback()
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception:
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi không xác định"}, status=500)
    finally:
        if cursor:
            cursor.close()
        if db and db.open:
            db.close()


@csrf_exempt
@require_POST
def share_schedule_via_email(request):
    db = None
    cursor = None
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        schedule_id = data.get("schedule_id")
        recipient_email = data.get("email")

        if not user_id:
            return JsonResponse({"error": "Thiếu user_id"}, status=400)
        if not schedule_id:
            return JsonResponse({"error": "Thiếu schedule_id"}, status=400)
        if not recipient_email:
            return JsonResponse({"error": "Thiếu email người nhận"}, status=400)

        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()

        cursor.execute("SELECT user_id FROM schedules WHERE id = %s", [schedule_id])
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return JsonResponse({"error": "Không có quyền chia sẻ"}, status=403)

        cursor.execute("SELECT full_name FROM users WHERE id = %s", [user_id])
        user_result = cursor.fetchone()
        if not user_result:
            return JsonResponse({"error": "Người dùng không tồn tại"}, status=404)
        full_name = user_result[0]

        cursor.execute("SELECT share_link FROM sharedLinks WHERE schedule_id = %s", [schedule_id])
        existing_link = cursor.fetchone()
        if existing_link:
            share_link = existing_link[0]
        else:
            share_token = str(uuid.uuid4()).lower()
            share_link = f"http://{request.get_host()}/recommend/view-schedule/{share_token}/"
            cursor.execute(
                "INSERT INTO sharedLinks (schedule_id, share_link) VALUES (%s, %s)",
                [schedule_id, share_link]
            )
            db.commit()

        subject = 'Lịch trình du lịch được chia sẻ từ FinTrip'
        message = f'''Xin chào,

Bạn vừa nhận được một lịch trình du lịch được chia sẻ qua ứng dụng FinTrip – trợ lý đồng hành đáng tin cậy trong mọi hành trình khám phá.

Người dùng {full_name} đã chia sẻ với bạn một kế hoạch chi tiết bao gồm các điểm tham quan nổi bật và những gợi ý hấp dẫn cho chuyến đi.

Vui lòng nhấn vào đường link sau để xem chi tiết lịch trình:
{share_link}

Chúc bạn có những trải nghiệm tuyệt vời cùng FinTrip!

Trân trọng,  
Đội ngũ FinTrip'''
        email_from = settings.EMAIL_HOST_USER
        recipient_list = [recipient_email]
        send_mail(subject, message, email_from, recipient_list)

        return JsonResponse({"message": "Chia sẻ thành công qua email", "share_link": share_link}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except MySQLdb.IntegrityError:
        return JsonResponse({"error": "Liên kết chia sẻ đã tồn tại"}, status=409)
    except MySQLdb.Error:
        if db:
            db.rollback()
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Lỗi không xác định: {str(e)}"}, status=500)
    finally:
        if cursor:
            cursor.close()
        if db and db.open:
            db.close()


@csrf_exempt
@require_GET
def get_schedule(request):
    # Lấy user_id từ query string
    user_id = request.GET.get('user_id')
    if not user_id:
        return JsonResponse({"error": "Thiếu user_id"}, status=400)

    # Xác thực user_id là số nguyên
    try:
        user_id = int(user_id)
    except ValueError:
        return JsonResponse({"error": "user_id phải là số nguyên"}, status=400)

    try:
        with MySQLdb.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                passwd=MYSQL_PASSWORD,
                db=MYSQL_DB,
                port=MYSQL_PORT,
                charset=MYSQL_CHARSET
        ) as db:
            with db.cursor() as cursor:
                # Kiểm tra user tồn tại
                cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
                if not cursor.fetchone():
                    return JsonResponse({"error": "Không tìm thấy người dùng"}, status=404)

                # Lấy schedules
                cursor.execute("SELECT * FROM schedules WHERE user_id = %s", [user_id])
                columns = [desc[0] for desc in cursor.description]
                schedules = cursor.fetchall()

                # Chuyển đổi dữ liệu
                schedule_list = []
                for schedule in schedules:
                    schedule_dict = dict(zip(columns, schedule))
                    if 'created_at' in schedule_dict and schedule_dict['created_at']:
                        schedule_dict['created_at'] = schedule_dict['created_at'].isoformat()
                    schedule_list.append(schedule_dict)

                # Chuẩn bị response
                if not schedule_list:
                    response_data = {
                        "status": "success",
                        "data": {"schedules": []},
                        "message": "Không có lịch trình nào cho người dùng này"
                    }
                else:
                    response_data = {
                        "status": "success",
                        "data": {"schedules": schedule_list},
                        "message": "Lấy lịch trình thành công"
                    }
                logger.info("Travel schedule generated successfully")
                return JsonResponse(response_data, status=200)

    except MySQLdb.Error as e:
        logger.error(f"Database error: {e}")
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)



@require_GET
def view_schedule(request, schedule_id):
    db = None
    cursor = None
    try:
        # Kết nối đến cơ sở dữ liệu
        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()

        # Lấy thông tin lịch trình từ bảng schedules
        cursor.execute("SELECT name, created_at FROM schedules WHERE id = %s", [schedule_id])
        schedule = cursor.fetchone()
        if not schedule:
            return JsonResponse({"error": "Lịch trình không tồn tại"}, status=404)

        # Lấy thông tin khách sạn từ bảng hotels
        cursor.execute(
            """
            SELECT id, address, created_at, description, hotel_class, img_origin, link, location_rating, 
                   name, price, updated_at 
            FROM hotels 
            WHERE schedule_id = %s
            """,
            [schedule_id]
        )
        hotel = cursor.fetchone()
        hotel_data = None
        if hotel:
            # Xây dựng từ điển dữ liệu khách sạn
            columns = [desc[0] for desc in cursor.description]
            hotel_data = dict(zip(columns, hotel))

        # Lấy thông tin các ngày trong lịch trình từ bảng days
        cursor.execute(
            "SELECT id, day_index, date_str FROM days WHERE schedule_id = %s ORDER BY day_index",
            [schedule_id]
        )
        days = cursor.fetchall()

        # Tạo dữ liệu lịch trình
        schedule_data = {"name": schedule[0], "created_at": schedule[1], "days": []}
        for day in days:
            day_id, day_index, date_str = day
            # Lấy thông tin hành trình chi tiết từ bảng itineraries
            cursor.execute(
                """
                SELECT id, timeslot, food_title, food_rating, food_price, food_address, food_phone, 
                       food_link, food_image, place_title, place_rating, place_description, 
                       place_address, place_img, place_link, `order`, food_time, place_time
                FROM itineraries
                WHERE day_id = %s
                """,
                [day_id]
            )
            itineraries = cursor.fetchall()
            day_plan = {
                "day_index": day_index,
                "date_str": date_str,
                "itineraries": []
            }
            for item in itineraries:
                columns = [desc[0] for desc in cursor.description]
                itinerary_data = dict(zip(columns, item))
                day_plan["itineraries"].append(itinerary_data)
            schedule_data["days"].append(day_plan)

        # Tạo dữ liệu phản hồi
        response_data = {}
        if hotel_data:
            response_data["hotel"] = hotel_data
        response_data["schedule"] = schedule_data

        return JsonResponse(response_data, status=200)

    except MySQLdb.Error as e:
        logger.error(f"Database error: {e}")
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi không xác định"}, status=500)
    finally:
        # Đóng kết nối cơ sở dữ liệu
        if cursor:
            cursor.close()
        if db and db.open:
            db.close()

'''
End Save share view
'''

#######################################

'''
Admin để quản ly khách sạn
'''
@require_GET
def get_all_hotels(request):
    try:
        hotels = show_hotel_in_csv()
        if hotels is None or not hotels:
            return JsonResponse({"error": "Không có khách sạn nào trong danh sách hoặc file CSV không tồn tại."}, status=404)

        return JsonResponse({
            "hotels": hotels,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_all_hotels: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)


@require_GET
def get_hotel_by_name(request, name):
    try:
        hotels = show_hotel_in_csv()
        if hotels is None:
            return JsonResponse({"error": "File CSV không tồn tại."}, status=404)

        hotel = next((h for h in hotels if h["name"] == name), None)
        if not hotel:
            return JsonResponse({"error": f"Không tìm thấy khách sạn với tên '{name}'."}, status=404)

        return JsonResponse({
            "hotel": hotel,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_hotel_by_name: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)


@csrf_exempt
@require_POST
def update_hotel(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        hotel_name = data.get("name", "").strip()

        if not hotel_name:
            return JsonResponse({"error": "Vui lòng cung cấp tên khách sạn (name)."}, status=400)

        update_data = {
            "name": hotel_name,
            "link": data.get("link", "").strip(),
            "description": data.get("description", "").strip(),
            "price": data.get("price", "").strip(),
            "name_nearby_place": data.get("name_nearby_place", "").strip(),
            "hotel_class": data.get("hotel_class", "").strip(),
            "img_origin": data.get("img_origin", "").strip(),
            "location_rating": data.get("location_rating", "").strip(),
            "province": data.get("province", "").strip()
        }

        try:
            if update_data["price"]:
                float(update_data["price"])
            if update_data["location_rating"]:
                float(update_data["location_rating"])
        except ValueError:
            return JsonResponse({"error": "Giá (price) hoặc đánh giá vị trí (location_rating) phải là số."}, status=400)

        updated = update_hotel_in_csv(hotel_name, update_data)
        if not updated:
            return JsonResponse({"error": f"Không tìm thấy khách sạn '{hotel_name}' để cập nhật."}, status=404)

        return JsonResponse({
            "message": "Cập nhật thông tin khách sạn thành công!",
            "updated_hotel": update_data,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in update_hotel: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)


@csrf_exempt
@require_POST
def delete_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        hotel_name = data.get("name", "").strip()

        if not hotel_name:
            return JsonResponse({"error": "Vui lòng cung cấp tên khách sạn (name)."}, status=400)

        deleted = delete_hotel_in_csv(hotel_name)
        if not deleted:
            return JsonResponse({"error": "Không tìm thấy khách sạn để xóa."}, status=404)

        return JsonResponse({
            "message": "Xóa khách sạn thành công!",
            "deleted_hotel_name": hotel_name,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in delete_hotel: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)


@require_GET
def search_hotels_by_province(request):
    try:
        province = request.GET.get("province", "").strip()
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tên tỉnh (province)."}, status=400)

        hotels = process_hotel_data_from_csv(province)
        if not hotels:
            return JsonResponse({"error": f"Không tìm thấy khách sạn nào ở tỉnh {province} hoặc file CSV không tồn tại."}, status=404)

        return JsonResponse({
            "hotels": hotels,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in search_hotels_by_province: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@csrf_exempt
@require_POST
def create_user(request):
    """Tạo người dùng mới."""
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip()
        status = data.get("status", "active").strip()
        role_id = data.get("role_id")

        if not all([email, password, full_name, role_id]):
            return JsonResponse({"error": "Thiếu email, password, full_name hoặc role_id"}, status=400)

        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
            return JsonResponse({"error": "Email không hợp lệ"}, status=400)

        if status not in ['active', 'inactive', 'banned']:
            return JsonResponse({"error": "Status không hợp lệ"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        # Kiểm tra role_id có tồn tại trong bảng Roles
        cursor.execute("SELECT id FROM roles WHERE id = %s", [int(role_id)])
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return JsonResponse({"error": "Role ID không tồn tại"}, status=400)

        # Kiểm tra email trùng lặp trong bảng Users
        cursor.execute("SELECT id FROM users WHERE email = %s", [email])
        if cursor.fetchone():
            cursor.close()
            db.close()
            return JsonResponse({"error": "Email đã tồn tại trong bảng Users"}, status=400)

        # Kiểm tra email trùng lặp trong bảng auth_user
        if User.objects.filter(username=email).exists():
            cursor.close()
            db.close()
            return JsonResponse({"error": "Email đã tồn tại trong hệ thống xác thực"}, status=400)

        # Tạo người dùng trong bảng auth_user của Django
        django_user = User.objects.create_user(username=email, email=email, password=password)
        django_user_id = django_user.id

        # Mã hóa mật khẩu cho bảng Users
        hashed_password = hash_password(password)
        cursor.execute(
            "INSERT INTO users (id, email, password, full_name, status, role_id) VALUES (%s, %s, %s, %s, %s, %s)",
            [django_user_id, email, hashed_password, full_name, status, int(role_id)]
        )
        db.commit()

        cursor.close()
        db.close()
        return JsonResponse({"message": "Tạo người dùng thành công", "user_id": django_user_id}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in create_user: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_user(request, user_id):
    try:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "User ID must be an integer."}, status=400)

        with MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        ) as db:
            with db.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
                if not cursor.fetchone():
                    return JsonResponse({"error": "User not found."}, status=404)

                tables_with_user_id = [
                    "schedules",
                    "travel_plan",
                    "blog_post",
                    "comments",
                    "notifications",
                    "password_reset_tokens",
                    "recommendation",
                    "replies",
                    "room_members",
                    "travel_groups",
                    "activities"
                ]

                cursor.execute("START TRANSACTION")

                for table in tables_with_user_id:
                    cursor.execute(f"DELETE FROM {table} WHERE user_id = %s", [user_id])

                cursor.execute("DELETE FROM friendships WHERE sender_id = %s OR receiver_id = %s", [user_id, user_id])
                cursor.execute("DELETE FROM group_messages WHERE sender_id = %s", [user_id])
                cursor.execute("DELETE FROM messages WHERE sender_id = %s OR receiver_id = %s", [user_id, user_id])
                cursor.execute("DELETE FROM chat_room WHERE created_by = %s", [user_id])

                cursor.execute("DELETE FROM users WHERE id = %s", [user_id])

                db.commit()

        return JsonResponse({
            "message": "User deleted successfully!",
            "user_id": user_id
        }, status=200)

    except MySQLdb.OperationalError as e:
        traceback.print_exc()
        return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)


@require_GET
def get_user(request, user_id):
    try:
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        query = """
            SELECT u.id, u.full_name, u.email, r.role_name, u.status
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.id = %s
        """
        cursor.execute(query, (user_id,))
        row = cursor.fetchone()

        if row:
            user = {
                "id": row[0],
                "full_name": row[1],
                "email": row[2],
                "role_name": row[3],
                "status": row[4]
            }
            cursor.close()
            db.close()
            return JsonResponse({"user": user}, status=200)
        else:
            cursor.close()
            db.close()
            return JsonResponse({"error": "User not found"}, status=404)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def update_user(request):
    try:
        data = json.loads(request.body)
        user_id = data.get("id")

        if not user_id:
            return JsonResponse({"error": "Thiếu trường bắt buộc: user_id"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute("SELECT email, full_name, status, role_id FROM users WHERE id = %s", [user_id])
        user = cursor.fetchone()
        if not user:
            cursor.close()
            db.close()
            return JsonResponse({"error": "Người dùng không tồn tại."}, status=404)

        current_email, current_full_name, current_status, current_role_id = user

        email = data.get("email", "").strip()
        if email:
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if not re.match(email_pattern, email):
                cursor.close()
                db.close()
                return JsonResponse({"error": "Email không hợp lệ."}, status=400)
        else:
            email = current_email

        full_name = data.get("full_name", "").strip()
        if not full_name:
            full_name = current_full_name

        status = data.get("status", "").strip()
        if status:
            valid_statuses = ['active', 'inactive', 'banned']
            if status not in valid_statuses:
                cursor.close()
                db.close()
                return JsonResponse({"error": "Status phải là 'active', 'inactive', hoặc 'banned'."}, status=400)
        else:
            status = current_status

        role_name = data.get("role_name", "").strip()
        if role_name:
            cursor.execute("SELECT id FROM roles WHERE role_name = %s", [role_name])
            role = cursor.fetchone()
            if not role:
                cursor.close()
                db.close()
                return JsonResponse({"error": "Role name không tồn tại."}, status=400)
            role_id = role[0]
        else:
            role_id = current_role_id

        sql = """
            UPDATE users 
            SET email = %s, full_name = %s, status = %s, role_id = %s
            WHERE id = %s
        """
        cursor.execute(sql, [email, full_name, status, role_id, user_id])
        db.commit()

        try:
            django_user = User.objects.get(id=user_id)
            django_user.username = email
            django_user.email = email
            django_user.save()
        except User.DoesNotExist:
            pass

        cursor.close()
        db.close()

        return JsonResponse({
            "message": "Cập nhật thông tin người dùng thành công!",
            "user_id": user_id,
            "updated_info": {
                "email": email,
                "full_name": full_name,
                "status": status,
                "role_name": role_name if role_name else None
            }
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def user_manage(request):
    try:
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        query = """
            SELECT u.id, u.full_name, u.email, r.role_name, u.status
            FROM users u
            JOIN roles r ON u.role_id = r.id
        """
        cursor.execute(query)
        results = cursor.fetchall()

        users = [{"id": row[0], "full_name": row[1], "email": row[2], "role_name": row[3], "status": row[4]} for row in results]

        cursor.close()
        db.close()

        return JsonResponse({"users": users}, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def search_user(request):
    try:
        search_term = request.GET.get("userinfo", "").strip()
        if not search_term:
            return JsonResponse({"error": "Thiếu tham số tìm kiếm 'userinfo'."}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        query = """
            SELECT u.id, u.full_name, u.email, r.role_name, u.status
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.full_name LIKE %s OR u.email LIKE %s
        """
        cursor.execute(query, [f'%{search_term}%', f'%{search_term}%'])
        results = cursor.fetchall()

        users = [{"id": row[0], "full_name": row[1], "email": row[2], "role_name": row[3], "status": row[4]} for row in results]

        cursor.close()
        db.close()

        return JsonResponse({"users": users}, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def filter_by_role(request):
    try:
        role_name = request.GET.get("role", "").strip()
        if not role_name:
            return JsonResponse({"error": "Thiếu tham số 'role'."}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        query = """
            SELECT u.id, u.full_name, u.email, r.role_name, u.status
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE r.role_name = %s
        """
        cursor.execute(query, [role_name])
        results = cursor.fetchall()

        users = [{"id": row[0], "full_name": row[1], "email": row[2], "role_name": row[3], "status": row[4]} for row in results]

        cursor.close()
        db.close()

        return JsonResponse({"users": users}, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def filter_by_status(request):
    try:
        status = request.GET.get("status", "").strip()
        if not status:
            return JsonResponse({"error": "Thiếu tham số 'status'."}, status=400)

        valid_statuses = ['active', 'inactive', 'banned']
        if status not in valid_statuses:
            return JsonResponse({"error": "Status phải là 'active', 'inactive', hoặc 'banned'."}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        query = """
            SELECT u.id, u.full_name, u.email, r.role_name, u.status
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.status = %s
        """
        cursor.execute(query, [status])
        results = cursor.fetchall()

        users = [{"id": row[0], "full_name": row[1], "email": row[2], "role_name": row[3], "status": row[4]} for row in results]

        cursor.close()
        db.close()

        return JsonResponse({"users": users}, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


## Place
@csrf_exempt
@require_GET
def get_all_place_admin(request):
    try:
        places = get_place_homepage()
        if not places:
            return JsonResponse({"error": "Error File..."}, status=404)

        return JsonResponse({
            "places": places,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_all_place_homepage: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@csrf_exempt
@require_POST
def add_place(request):
    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()
        title = data.get("title", "").strip()
        rating = data.get("rating", "").strip()
        description = data.get("description", "").strip()
        address = data.get("address", "").strip()
        img = data.get("img", "").strip()
        types = data.get("types", [])

        # Kiểm tra các trường bắt buộc
        if not all([province, title, rating, address, img]):
            return JsonResponse({"error": "Thiếu các trường bắt buộc: province, title, rating, address, img, link"}, status=400)

        # Kiểm tra định dạng rating
        try:
            rating = float(rating)
            if not 0 <= rating <= 5:
                return JsonResponse({"error": "Rating phải từ 0 đến 5."}, status=400)
        except ValueError:
            return JsonResponse({"error": "Rating phải là số."}, status=400)

        # Kiểm tra xem place đã tồn tại chưa
        if place_exists(province, title):
            return JsonResponse({"error": "Địa điểm đã tồn tại."}, status=400)

        # Đọc file Excel và thêm dữ liệu mới
        df = pd.read_excel(PLACE_FILE)
        new_row = {
            'province': province,
            'title': title,
            'rating': rating,
            'description': description,
            'address': address,
            'img': img,
            'types': str(types)
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_excel(PLACE_FILE, index=False)

        return JsonResponse({"message": "Thêm địa điểm thành công!"}, status=201)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_place(request):

    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()
        title = data.get("title", "").strip()

        if not all([province, title]):
            return JsonResponse({"error": "Thiếu các trường bắt buộc: province, title"}, status=400)

        normalized_province = normalize_text(province)
        normalized_title = normalize_text(title)

        df = pd.read_excel(PLACE_FILE)
        df['normalized_province'] = df['province'].apply(normalize_text)
        df['normalized_title'] = df['title'].apply(normalize_text)

        mask = (df['normalized_province'] == normalized_province) & (df['normalized_title'] == normalized_title)
        if mask.sum() == 0:
            return JsonResponse({"error": "Địa điểm không tồn tại."}, status=404)

        df = df[~mask]
        df.drop(columns=['normalized_province', 'normalized_title'], inplace=True)
        df.to_excel(PLACE_FILE, index=False)

        return JsonResponse({"message": "Xóa địa điểm thành công!"}, status=200)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["PUT"])
def update_place(request):

    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()
        title = data.get("title", "").strip()
        updates = data.get("updates", {})

        if not all([province, title]):
            return JsonResponse({"error": "Thiếu các trường bắt buộc: province, title"}, status=400)

        normalized_province = normalize_text(province)
        normalized_title = normalize_text(title)

        df = pd.read_excel(PLACE_FILE)
        df['normalized_province'] = df['province'].apply(normalize_text)
        df['normalized_title'] = df['title'].apply(normalize_text)

        mask = (df['normalized_province'] == normalized_province) & (df['normalized_title'] == normalized_title)
        if mask.sum() == 0:
            return JsonResponse({"error": "Địa điểm không tồn tại."}, status=404)

        for key, value in updates.items():
            if key in df.columns:
                if key == 'rating':
                    try:
                        value = float(value)
                        if not 0 <= value <= 5:
                            return JsonResponse({"error": "Rating phải từ 0 đến 5."}, status=400)
                    except ValueError:
                        return JsonResponse({"error": "Rating phải là số."}, status=400)
                df.loc[mask, key] = value

        df.drop(columns=['normalized_province', 'normalized_title'], inplace=True)
        df.to_excel(PLACE_FILE, index=False)

        return JsonResponse({"message": "Cập nhật địa điểm thành công!"}, status=200)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


#Food
@csrf_exempt
@require_GET
def get_all_food_admin(request):
    try:
        foods = get_food_homepage()
        if not foods:
            return JsonResponse({"error": "Error File..."}, status=404)

        return JsonResponse({
            "foods": foods,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_all_food_homepage: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@csrf_exempt
@require_POST
def add_food(request):
    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()
        title = data.get("title", "").strip()
        rating = data.get("rating", "").strip()
        price = data.get("price", "").strip()
        address = data.get("address", "").strip()
        phone = data.get("phone", "").strip()
        link = data.get("link", "").strip()
        service = data.get("service", [])
        img = data.get("img", "").strip()

        # Kiểm tra các trường bắt buộc
        if not all([province, title, rating, address, img]):
            return JsonResponse({"error": "Thiếu các trường bắt buộc: province, title, rating, address, img"}, status=400)

        # Kiểm tra định dạng rating
        try:
            rating = float(rating)
            if not 0 <= rating <= 5:
                return JsonResponse({"error": "Rating phải từ 0 đến 5."}, status=400)
        except ValueError:
            return JsonResponse({"error": "Rating phải là số."}, status=400)

        # Kiểm tra xem food đã tồn tại chưa
        if food_exists(province, title):
            return JsonResponse({"error": "Món ăn đã tồn tại."}, status=400)

        # Đọc file CSV và thêm dữ liệu mới
        df = pd.read_csv(FOOD_FILE)
        new_row = {
            'Province': province,
            'Title': title,
            'Rating': rating,
            'Price': price,
            'Address': address,
            'Phone': phone,
            'Link': link,
            'Service': str(service),
            'Image': img
        }
        new_df = pd.DataFrame([new_row])  # Convert the dictionary to a DataFrame
        df = pd.concat([df, new_df], ignore_index=True)  # Use pd.concat instead of append
        df.to_csv(FOOD_FILE, index=False)

        return JsonResponse({"message": "Thêm món ăn thành công!"}, status=201)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_food(request):

    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()
        title = data.get("title", "").strip()

        if not all([province, title]):
            return JsonResponse({"error": "Thiếu các trường bắt buộc: province, title"}, status=400)

        normalized_province = normalize_text(province)
        normalized_title = normalize_text(title)

        df = pd.read_csv(FOOD_FILE)
        df['normalized_province'] = df['Province'].apply(normalize_text)
        df['normalized_title'] = df['Title'].apply(normalize_text)

        mask = (df['normalized_province'] == normalized_province) & (df['normalized_title'] == normalized_title)
        if mask.sum() == 0:
            return JsonResponse({"error": "Món ăn không tồn tại."}, status=404)

        df = df[~mask]
        df.drop(columns=['normalized_province', 'normalized_title'], inplace=True)
        df.to_csv(FOOD_FILE, index=False)

        return JsonResponse({"message": "Xóa món ăn thành công!"}, status=200)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def update_food(request):
    try:
        data = json.loads(request.body)
        province = data.get("province", "").strip()
        title = data.get("title", "").strip()
        updates = data.get("updates", {})

        if not all([province, title]):
            return JsonResponse({"error": "Thiếu các trường bắt buộc: province, title"}, status=400)

        normalized_province = normalize_text(province)
        normalized_title = normalize_text(title)

        df = pd.read_csv(FOOD_FILE)
        df['normalized_province'] = df['Province'].apply(normalize_text)
        df['normalized_title'] = df['Title'].apply(normalize_text)

        mask = (df['normalized_province'] == normalized_province) & (df['normalized_title'] == normalized_title)
        if mask.sum() == 0:
            return JsonResponse({"error": "Món ăn không tồn tại."}, status=404)

        for key, value in updates.items():
            if key in df.columns:
                if key == 'Rating':
                    try:
                        value = float(value)
                        if not 0 <= value <= 5:
                            return JsonResponse({"error": "Rating phải từ 0 đến 5."}, status=400)
                    except ValueError:
                        return JsonResponse({"error": "Rating phải là số."}, status=400)
                df.loc[mask, key] = value

        df.drop(columns=['normalized_province', 'normalized_title'], inplace=True)
        df.to_csv(FOOD_FILE, index=False)

        return JsonResponse({"message": "Cập nhật món ăn thành công!"}, status=200)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


'''
end Admin để quản ly khách sạn
'''

# API tìm kiếm tỉnh/thành phố
@csrf_exempt
@require_POST
def search_province(request):
    try:
        if not request.body:
            return JsonResponse({"error": "Không có dữ liệu trong request body."}, status=400)

        data = json.loads(request.body.decode('utf-8'))
        province = data.get("destinationInput", "").strip()
        query = data.get("query", "").strip()

        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)
        if len(province) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        food_df, place_df, hotel_df = load_data(FOOD_FILE, PLACE_FILE, HOTEL_FILE)

        normalized_province = normalize_text(province)
        normalized_query = normalize_text(query) if query else None

        def filter_data(df, province_col='province', name_col='title'):
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.dropna(subset=[province_col, name_col])
            if normalized_province and normalized_query:
                return df[
                    df[province_col].str.contains(normalized_province, case=False, na=False) &
                    df[name_col].str.contains(normalized_query, case=False, na=False)
                ]
            elif normalized_province:
                return df[df[province_col].str.contains(normalized_province, case=False, na=False)]
            elif normalized_query:
                return df[df[name_col].str.contains(normalized_query, case=False, na=False)]
            else:
                return df

        filtered_food = filter_data(food_df, province_col='province', name_col='title')
        filtered_place = filter_data(place_df, province_col='province', name_col='title')
        filtered_hotel = filter_data(hotel_df, province_col='province', name_col='name')

        food_list = [{
            "province": food.get("province", ""),
            "title": food.get("title", ""),
            "rating": float(food["rating"]) if pd.notna(food.get("rating")) else None,
            "price": food.get("Price", ""),
            "address": food.get("address", ""),
            "phone": food.get("Phone", ""),
            "link": food.get("Link", ""),
            "service": food.get("types", []),
            "image": food.get("img", "")
        } for food in filtered_food.to_dict('records')]

        place_list = [{
            "province": place.get("province", ""),
            "title": place.get("title", ""),
            "rating": float(place["rating"]) if pd.notna(place.get("rating")) else None,
            "description": place.get("description", ""),
            "address": place.get("address", ""),
            "img": place.get("img", ""),
            "types": place.get("types", []),
            "link": place.get("link", "")
        } for place in filtered_place.to_dict('records')]

        hotel_list = [{
            "province": hotel.get("province", ""),
            "name": hotel.get("name", ""),
            "location_rating": float(hotel["location_rating"]) if pd.notna(hotel.get("location_rating")) else None,
            "description": hotel.get("description", ""),
            "address": hotel.get("address", ""),
            "img": hotel.get("img_origin", ""),
            "link": hotel.get("link", ""),
            "price": hotel.get("price", ""),
            "name_nearby_place": hotel.get("name_nearby_place", ""),
            "hotel_class": hotel.get("hotel_class", ""),
            "animates": hotel.get("animates", "")
        } for hotel in filtered_hotel.to_dict('records')] if hotel_df is not None else []

        if not food_list and not place_list and not hotel_list:
            return JsonResponse({"error": "Không tìm thấy hoạt động nào cho tỉnh/thành phố này."}, status=404)

        return JsonResponse({
            "foods": food_list,
            "places": place_list,
            "hotels": hotel_list,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in search_province: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

# API lấy danh sách thành phố nổi bật
@csrf_exempt
@require_GET
def get_top_cities(request):
    try:
        num_cities = int(request.GET.get('num_cities', 10))
        result = get_city_to_be_miss(num_cities=num_cities)

        if "error" in result:
            return JsonResponse({"error": result["error"]}, status=404 if "Không có dữ liệu" in result["error"] else 500)

        return JsonResponse(result, status=200)

    except ValueError:
        return JsonResponse({"error": "Số lượng thành phố phải là số nguyên."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_top_cities: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

# API tìm kiếm địa điểm
@csrf_exempt
@require_POST
def search_place(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        province = data.get("destinationInput", "").strip()
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        if len(province) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)

        normalized_province = normalize_text(province)

        places = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')

        place_list = [{
            "province": place.get("province"),
            "title": place.get("title"),
            "rating": float(place.get("rating")) if pd.notna(place.get("rating")) else None,
            "description": place.get("description"),
            "address": place.get("address"),
            "img": place.get("img"),
            "types": place.get("types"),
            "link": place.get("link")
        } for place in places]

        if not place_list:
            return JsonResponse({"error": "Không tìm thấy hoạt động nào cho tỉnh/thành phố này."}, status=404)

        return JsonResponse({
            "places": place_list,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in search_place: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

# API tìm kiếm món ăn
@csrf_exempt
@require_POST
def search_food(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        province = data.get("destinationInput", "").strip()
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        if len(province) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        food_df, place_df, _ = load_data(FOOD_FILE, PLACE_FILE)

        normalized_province = normalize_text(province)

        foods = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')

        food_list = [{
            "province": food.get("province"),
            "title": food.get("title"),
            "rating": float(food.get("rating")) if pd.notna(food.get("rating")) else None,
            "price": food.get("Price"),
            "address": food.get("address"),
            "phone": food.get("Phone"),
            "link": food.get("Link"),
            "service": food.get("types"),
            "image": food.get("img")
        } for food in foods]

        if not food_list:
            return JsonResponse({"error": "Không tìm thấy hoạt động nào cho tỉnh/thành phố này."}, status=404)

        return JsonResponse({
            "foods": food_list,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in search_food: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

'''''
Homepage APIs
'''''
@require_GET
def get_all_hotels_homepage(request):
    try:
        hotels = get_hotel_homepage()
        if not hotels:
            return JsonResponse({"error": "Error File..."}, status=404)

        return JsonResponse({
            "hotels": hotels,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_all_hotels_homepage: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@require_GET
def get_all_place_homepage(request):
    try:
        places = get_place_homepage()
        if not places:
            return JsonResponse({"error": "Error File..."}, status=404)

        return JsonResponse({
            "places": places,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_all_place_homepage: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@csrf_exempt
@require_POST
def select_place(request):
    try:
        data = json.loads(request.body)
        place_info = data.get("place_info")

        if not place_info or "province" not in place_info:
            return JsonResponse({"error": "Thiếu thông tin địa điểm hoặc tỉnh"}, status=400)

        request.session["selected_province"] = place_info["province"]

        place_details = {key: value for key, value in place_info.items() if key != "province"}
        request.session["selected_place_info"] = place_details
        return JsonResponse({"message": "Địa điểm và province đã được lưu vào session"}, status=200)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in select_place: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@require_GET
def get_all_food_homepage(request):
    try:
        foods = get_food_homepage()
        if not foods:
            return JsonResponse({"error": "Error File..."}, status=404)

        return JsonResponse({
            "foods": foods,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, json_dumps_params={"ensure_ascii": False}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_all_food_homepage: {str(e)}")
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

'''
To do list
'''

@csrf_exempt
@require_POST
def create_todolist_activity(request):
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "Thiếu user_id trong yêu cầu"}, status=400)

        activities = data.get("activities", [])
        if not isinstance(activities, list):
            activities = [data]

        if not activities:
            return JsonResponse({"error": "Không có hoạt động nào để lưu"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        for activity in activities:
            note_activities = activity.get("note_activities", "").strip()
            description = activity.get("description", "").strip()
            date_activities_str = activity.get("date_activities", "").strip()
            status = activity.get("status", 0)
            itinerary_id = activity.get("itinerary_id", None)
            date_plan_str = activity.get("date_plan", "").strip()

            if not note_activities:
                continue

            if itinerary_id:
                cursor.execute("SELECT day_id FROM itineraries WHERE id = %s", [itinerary_id])
                day_id = cursor.fetchone()
                if not day_id:
                    continue
                day_id = day_id[0]

                cursor.execute("SELECT schedule_id, date_str FROM days WHERE id = %s", [day_id])
                result = cursor.fetchone()
                if not result:
                    continue
                schedule_id, date_str = result
                date_activities = date_str

                cursor.execute("SELECT MIN(date_str) FROM days WHERE schedule_id = %s", [schedule_id])
                start_date = cursor.fetchone()[0]
                date_plan = start_date
            else:
                if date_plan_str:
                    try:
                        date_plan = datetime.strptime(date_plan_str, "%Y-%m-%d").date()
                    except ValueError:
                        return JsonResponse({"error": "Định dạng date_plan không hợp lệ"}, status=400)
                else:
                    date_plan = datetime.now().date()

                if date_activities_str:
                    try:
                        date_activities = datetime.strptime(date_activities_str, "%Y-%m-%d").date()
                    except ValueError:
                        return JsonResponse({"error": "Định dạng date_activities không hợp lệ"}, status=400)
                else:
                    date_activities = date_plan

            cursor.execute(
                """
                INSERT INTO activities (user_id, itinerary_id, note_activities, description, date_activities, status, date_plan)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [user_id, itinerary_id, note_activities, description, date_activities, status, date_plan]
            )

        db.commit()
        cursor.close()
        db.close()

        return JsonResponse({"message": "Tạo hoạt động thành công"}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Lỗi server: {str(e)}"}, status=500)

@csrf_exempt
@require_GET
def get_todolist_activities(request):
    try:
        user_id = request.GET.get("user_id")
        if not user_id:
            return JsonResponse({"error": "Thiếu user_id trong query parameters"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT activity_id, itinerary_id, note_activities, description, date_activities, status, date_plan
            FROM activities WHERE user_id = %s
            """,
            [user_id]
        )
        activities = cursor.fetchall()

        activity_list = [{
            "activity_id": row[0],
            "itinerary_id": row[1] if row[1] is not None else None,
            "note_activities": row[2],
            "description": row[3],
            "date_activities": row[4].isoformat() if row[4] else None,
            "status": row[5],
            "date_plan": row[6].isoformat() if row[6] else None
        } for row in activities]

        cursor.close()
        db.close()

        return JsonResponse({"activities": activity_list}, status=200)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in get_todolist_activities: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_POST
def update_todolist_activities(request):
    try:
        data = json.loads(request.body)
        activity_id = data.get("activity_id")
        user_id = data.get("user_id")
        note_activities = data.get("note_activities")
        description = data.get("description")
        date_activities = data.get("date_activities")
        status = data.get("status")
        date_plan = data.get("date_plan")
        itinerary_id = data.get("itinerary_id", None)

        if not activity_id or not user_id:
            return JsonResponse({"error": "Thiếu activity_id hoặc user_id"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) FROM activities WHERE activity_id = %s AND user_id = %s
            """,
            [activity_id, user_id]
        )
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.close()
            db.close()
            return JsonResponse({"error": "Hoạt động không tồn tại hoặc không thuộc về user này"}, status=404)

        update_fields = []
        params = []

        # Xóa các khóa Redis nếu thay đổi các trường liên quan
        if date_activities is not None or status is not None:
            # Xóa khóa activity_reminder
            activity_reminder_key = f"activity_reminder:{activity_id}:*"
            for key in redis_client.keys(activity_reminder_key):
                redis_client.delete(key)

        if date_plan is not None or status is not None:
            # Xóa khóa trip_reminder
            trip_reminder_key = f"trip_reminder:{activity_id}:*"
            for key in redis_client.keys(trip_reminder_key):
                redis_client.delete(key)

        if note_activities is not None:
            update_fields.append("note_activities = %s")
            params.append(note_activities)
        if description is not None:
            update_fields.append("description = %s")
            params.append(description)
        if date_activities is not None:
            update_fields.append("date_activities = %s")
            params.append(date_activities)
        if status is not None:
            update_fields.append("status = %s")
            params.append(status)
            # Nếu status không còn là 0, ngăn gửi email
            if status != 0:
                activity_reminder_key = f"activity_reminder:{activity_id}:*"
                for key in redis_client.keys(activity_reminder_key):
                    redis_client.delete(key)
                redis_client.set(f"activity_reminder:{activity_id}:block", "sent")
                trip_reminder_key = f"trip_reminder:{activity_id}:*"
                for key in redis_client.keys(trip_reminder_key):
                    redis_client.delete(key)
                redis_client.set(f"trip_reminder:{activity_id}:block", "sent")
        if date_plan is not None:
            update_fields.append("date_plan = %s")
            params.append(date_plan)
        if itinerary_id is not None:
            update_fields.append("itinerary_id = %s")
            params.append(itinerary_id)
        else:
            update_fields.append("itinerary_id = NULL")

        if not update_fields:
            cursor.close()
            db.close()
            return JsonResponse({"error": "Không có trường nào để cập nhật"}, status=400)

        update_query = "UPDATE activities SET " + ", ".join(update_fields) + " WHERE activity_id = %s"
        params.append(activity_id)

        cursor.execute(update_query, params)
        db.commit()

        cursor.close()
        db.close()

        return JsonResponse({"message": "Cập nhật thành công"}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in update_activity: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_POST
def delete_todolist_activities(request):
    try:
        data = json.loads(request.body)
        activity_id = data.get("activity_id")
        user_id = data.get("user_id")

        if not activity_id or not user_id:
            return JsonResponse({"error": "Thiếu activity_id hoặc user_id"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute(
            """
            DELETE FROM activities WHERE activity_id = %s AND user_id = %s
            """,
            [activity_id, user_id]
        )
        if cursor.rowcount == 0:
            cursor.close()
            db.close()
            return JsonResponse({"error": "Hoạt động không tồn tại hoặc không thuộc về user này"}, status=404)

        # Xóa tất cả khóa Redis liên quan đến hoạt động này
        activity_reminder_key = f"activity_reminder:{activity_id}:*"
        for key in redis_client.keys(activity_reminder_key):
            redis_client.delete(key)
        trip_reminder_key = f"trip_reminder:{activity_id}:*"
        for key in redis_client.keys(trip_reminder_key):
            redis_client.delete(key)

        db.commit()
        cursor.close()
        db.close()

        return JsonResponse({"message": "Xóa thành công"}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)