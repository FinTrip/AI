import json
import os
import re
from django.core.cache import cache

import pandas as pd
import uuid
import traceback
from datetime import datetime, date
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.views.decorators.http import require_POST, require_GET
from rest_framework import status
from django.conf import settings
import MySQLdb
import jwt
import logging
from django.contrib.auth import login, logout
from django.contrib.auth.models import User

from .CheckException import validate_request, check_missing_fields, check_field_length, check_province_format, check_date_format, check_date_logic
from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv, update_hotel_in_csv, delete_hotel_in_csv, show_hotel_in_csv, get_hotel_homepage
from .processed import load_data, recommend_schedule, FOOD_FILE, PLACE_FILE, HOTEL_FILE, normalize_text, \
    get_food_homepage, get_place_homepage, get_city_to_be_miss
from .weather import display_forecast, get_weather

# Thiết lập logging
logger = logging.getLogger(__name__)

# Cấu hình MySQL từ settings.py
MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'

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

# Hàm tạo người dùng mới
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
        cursor.execute("SELECT id FROM Roles WHERE id = %s", [int(role_id)])
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return JsonResponse({"error": "Role ID không tồn tại"}, status=400)

        # Kiểm tra email trùng lặp trong bảng Users
        cursor.execute("SELECT id FROM Users WHERE email = %s", [email])
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
            "INSERT INTO Users (id, email, password, full_name, status, role_id) VALUES (%s, %s, %s, %s, %s, %s)",
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

# Hàm xóa người dùng
@csrf_exempt
@require_POST
def delete_user(request):
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "Thiếu trường bắt buộc: user_id"}, status=400)

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "User ID phải là một số nguyên."}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute("SELECT id FROM Users WHERE id = %s", [user_id])
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return JsonResponse({"error": "Người dùng không tồn tại."}, status=404)

        cursor.execute("DELETE FROM Users WHERE id = %s", [user_id])
        db.commit()

        try:
            django_user = User.objects.get(id=user_id)
            django_user.delete()
        except User.DoesNotExist:
            pass

        cursor.close()
        db.close()

        return JsonResponse({
            "message": "Xóa người dùng thành công!",
            "user_id": user_id
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in delete_user: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()

# Hàm cập nhật người dùng
@csrf_exempt
@require_POST
def update_user(request):
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        if not user_id:
            return JsonResponse({"error": "Thiếu trường bắt buộc: user_id"}, status=400)

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "User ID phải là một số nguyên."}, status=400)

        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip()
        status = data.get("status", "").strip()
        role_id = data.get("role_id")

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        cursor.execute("SELECT email, password, full_name, status, role_id FROM Users WHERE id = %s", [user_id])
        user = cursor.fetchone()
        if not user:
            cursor.close()
            db.close()
            return JsonResponse({"error": "Người dùng không tồn tại."}, status=404)

        current_email, current_password, current_full_name, current_status, current_role_id = user

        if email:
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if not re.match(email_pattern, email):
                cursor.close()
                db.close()
                return JsonResponse({"error": "Email không hợp lệ."}, status=400)
            cursor.execute("SELECT id FROM Users WHERE email = %s AND id != %s", [email, user_id])
            if cursor.fetchone():
                cursor.close()
                db.close()
                return JsonResponse({"error": "Email đã tồn tại."}, status=400)
            if User.objects.filter(username=email).exclude(id=user_id).exists():
                cursor.close()
                db.close()
                return JsonResponse({"error": "Email đã tồn tại trong hệ thống xác thực."}, status=400)
        else:
            email = current_email

        if password:
            hashed_password = hash_password(password)
        else:
            hashed_password = current_password

        if not full_name:
            full_name = current_full_name

        if status:
            valid_statuses = ['active', 'inactive', 'banned']
            if status not in valid_statuses:
                cursor.close()
                db.close()
                return JsonResponse({"error": "Status phải là 'active', 'inactive', hoặc 'banned'."}, status=400)
        else:
            status = current_status

        if role_id is not None:
            try:
                role_id = int(role_id)
                cursor.execute("SELECT id FROM Roles WHERE id = %s", [role_id])
                if not cursor.fetchone():
                    cursor.close()
                    db.close()
                    return JsonResponse({"error": "Role ID không tồn tại."}, status=400)
            except (TypeError, ValueError):
                cursor.close()
                db.close()
                return JsonResponse({"error": "Role ID phải là một số nguyên."}, status=400)
        else:
            role_id = current_role_id

        sql = """
            UPDATE Users 
            SET email = %s, password = %s, full_name = %s, status = %s, role_id = %s
            WHERE id = %s
        """
        cursor.execute(sql, [email, hashed_password, full_name, status, role_id, user_id])
        db.commit()

        try:
            django_user = User.objects.get(id=user_id)
            django_user.username = email
            django_user.email = email
            if password:
                django_user.set_password(password)
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
                "role_id": role_id
            }
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in update_user: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()

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
            data = json.loads(request.body)
            email = data.get("email", "").strip()
            password = data.get("password", "").strip()

            logger.debug(f"Attempting login for email: {email}")
            if not email or not password:
                return JsonResponse({"error": "Thiếu email hoặc password"}, status=400)

            db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                                 db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
            cursor = db.cursor()
            cursor.execute("SELECT id, password FROM Users WHERE email = %s", [email])
            user = cursor.fetchone()

            if not user or not check_password(password, user[1]):
                cursor.close()
                db.close()
                return JsonResponse({"error": "Email hoặc mật khẩu không đúng"}, status=400)

            user_id = user[0]
            cursor.close()
            db.close()

            # Kiểm tra hoặc tạo người dùng trong auth_user
            try:
                django_user = User.objects.get(username=email)
                if django_user.id != user_id:
                    logger.error(f"User ID mismatch: auth_user.id={django_user.id}, Users.id={user_id}")
                    return JsonResponse({"error": "Lỗi đồng bộ người dùng, vui lòng liên hệ quản trị viên"}, status=500)
            except User.DoesNotExist:
                django_user = User.objects.create_user(id=user_id, username=email, email=email, password=password)

            login(request, django_user)
            request.session['user_id'] = user_id
            logger.debug(f"User logged in: {django_user.username}, Django User ID: {django_user.id}, Custom User ID: {user_id}")
            return JsonResponse({"message": "Đăng nhập thành công", "user_id": user_id}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Login error: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)

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
######## Q&A để lưu thông tin tỉnh
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

        request.session['selected_province'] = province
        request.session.modified = True
        logger.info(f"Province saved to session: {province}")
        return JsonResponse({"message": "Tỉnh đã được lưu."}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in set_province")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)

# API lưu ngày đi và về
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

        request.session['start_day'] = start_day
        request.session['end_day'] = end_day
        request.session.modified = True
        logger.info(f"Dates saved to session: start_day={start_day}, end_day={end_day}")
        return JsonResponse({"message": "Ngày đã được lưu."}, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in set_dates")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)

# API tìm kiếm chuyến bay
@csrf_exempt
@require_POST
def rcm_flight(request):
    try:
        data = json.loads(request.body)
        origin = data.get("origin", "").strip()
        destination = data.get("destination", request.session.get('selected_province', '')).strip()
        departure_date = data.get("departure_date", request.session.get('start_day', '')).strip()

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
        cache.set(cache_key, flight_info, timeout=3600)  # Now uses correct cache object
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
        search_term = data.get("destination", request.session.get('selected_province', '')).strip()

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
        cache.set(cache_key, hotel_info, timeout=3600)  # Now uses correct cache object
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
        province = data.get('province', request.session.get('selected_province', ''))
        start_day = data.get('start_day', request.session.get('start_day', ''))
        end_day = data.get('end_day', request.session.get('end_day', ''))
        flight_info = data.get('flight_info', None)
        hotel_info = data.get('hotel_info', None)

        if not province or not start_day or not end_day:
            logger.error("Missing required fields in travel_schedule")
            return JsonResponse({"error": "Thiếu thông tin tỉnh, ngày đi hoặc ngày về"}, status=400)

        cache_key_prefix = request.session.session_key
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



#######################################

'''
Admin để quản ly khách sạn
'''
@require_GET
def get_all_hotels(request):
    try:
        hotels = show_hotel_in_csv()
        if not hotels:
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

@csrf_exempt
@require_POST
def update_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
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

        updated = update_hotel_in_csv(hotel_name, update_data)
        if not updated:
            return JsonResponse({"error": "Không tìm thấy khách sạn để cập nhật."}, status=404)

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

# API lưu lịch trình
@csrf_exempt
@require_POST
def save_schedule(request):
    db = None
    cursor = None
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        if not user_id:
            return JsonResponse({"error": "Thiếu user_id trong yêu cầu"}, status=400)

        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()

        cursor.execute("SELECT id FROM Users WHERE id = %s", [user_id])
        user = cursor.fetchone()
        if not user:
            return JsonResponse({"error": "Không tìm thấy thông tin người dùng"}, status=404)

        schedule_name = data.get("schedule_name", "Lịch trình của tôi").strip()
        days_data = data.get("days", [])

        if not days_data:
            return JsonResponse({"error": "Danh sách ngày (days) không được rỗng"}, status=400)

        cursor.execute("INSERT INTO Schedules (user_id, name) VALUES (%s, %s)", [user_id, schedule_name])
        schedule_id = cursor.lastrowid

        # Lấy ngày bắt đầu từ ngày đầu tiên
        start_date = None
        for day in sorted(days_data, key=lambda x: x.get("day_index", 1)):
            date_str = day.get("date_str", "")
            date_match = re.search(r'\((\d{4}-\d{2}-\d{2})\)', date_str)
            if date_match:
                date_str = date_match.group(1)
            else:
                date_str = date_str[:10]
            if not start_date:
                start_date = date_str
            cursor.execute("INSERT INTO Days (schedule_id, day_index, date_str) VALUES (%s, %s, %s)",
                           [schedule_id, day.get("day_index", 1), date_str])
            day_id = cursor.lastrowid

            itinerary_list = day.get("itinerary", [])
            if not isinstance(itinerary_list, list):
                return JsonResponse({"error": "Itinerary phải là một danh sách"}, status=400)

            for item in itinerary_list:
                food_title = item.get("food_title")
                place_title = item.get("place_title")
                hotel_name = item.get("hotel_name")
                if not (food_title and food_title.strip()) and \
                   not (place_title and place_title.strip()) and \
                   not (hotel_name and hotel_name.strip()):
                    continue

                # Lấy food_time và place_time, cắt bớt nếu cần
                food_time = item.get("food_time", "")[:255] if item.get("food_time") else None
                place_time = item.get("place_time", "")[:255] if item.get("place_time") else None

                cursor.execute(
                    """
                    INSERT INTO Itineraries (
                        day_id, timeslot, food_title, food_rating, food_price, food_address, 
                        food_phone, food_link, food_image, place_title, place_rating, 
                        place_description, place_address, place_img, place_link, 
                        hotel_name, hotel_link, hotel_description, hotel_price, 
                        hotel_class, hotel_img_origin, hotel_location_rating, `order`,
                        food_time, place_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        day_id,
                        item.get("timeslot", "")[:20],
                        item.get("food_title", "")[:100],
                        item.get("food_rating"),
                        item.get("food_price", "")[:50],
                        item.get("food_address", "")[:200],
                        item.get("food_phone", "")[:20],
                        item.get("food_link", "")[:255],
                        item.get("food_image", "")[:255],
                        item.get("place_title", "")[:100],
                        item.get("place_rating"),
                        item.get("place_description"),
                        item.get("place_address", "")[:200],
                        item.get("place_img", "")[:255],
                        item.get("place_link", "")[:255],
                        item.get("hotel_name", "")[:100],
                        item.get("hotel_link", "")[:255],
                        item.get("hotel_description"),
                        item.get("hotel_price", "")[:50],
                        item.get("hotel_class", "")[:20],
                        item.get("hotel_img_origin", "")[:255],
                        item.get("hotel_location_rating"),
                        item.get("order"),
                        food_time,
                        place_time
                    ]
                )

        # Lưu start_day vào session
        if start_date:
            request.session['start_day'] = start_date
            request.session.modified = True

        share_token = str(uuid.uuid4()).lower()
        share_link = f"http://{request.get_host()}/recommend/view-schedule/{share_token}/"
        cursor.execute(
            "INSERT INTO SharedLinks (schedule_id, share_link) VALUES (%s, %s)",
            [schedule_id, share_link]
        )

        db.commit()
        return JsonResponse({
            "message": "Lịch trình đã được lưu thành công",
            "schedule_id": schedule_id,
            "share_link": share_link
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi không xác định"}, status=500)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'db' in locals() and db and db.open:
            db.close()


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

        # Verify schedule exists and belongs to user
        cursor.execute("SELECT user_id FROM Schedules WHERE id = %s", [schedule_id])
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return JsonResponse({"error": "Không có quyền chia sẻ"}, status=403)

        # Check for existing share link
        cursor.execute("SELECT share_link FROM SharedLinks WHERE schedule_id = %s", [schedule_id])
        existing_link = cursor.fetchone()
        if existing_link:
            return JsonResponse({"message": "Liên kết đã tồn tại", "share_link": existing_link[0]}, status=200)

        # Generate new share link with lowercase UUID and correct path
        share_token = str(uuid.uuid4()).lower()
        share_link = f"http://{request.get_host()}/recommend/view-schedule/{share_token}/"
        cursor.execute(
            "INSERT INTO SharedLinks (schedule_id, share_link) VALUES (%s, %s)",
            [schedule_id, share_link]
        )
        db.commit()

        return JsonResponse({"message": "Chia sẻ thành công", "share_link": share_link}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except MySQLdb.IntegrityError:
        return JsonResponse({"error": "Liên kết chia sẻ đã tồn tại"}, status=409)
    except MySQLdb.Error:
        if 'db' in locals() and db:
            db.rollback()
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception:
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi không xác định"}, status=500)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'db' in locals() and db and db.open:
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

        # Verify schedule exists and belongs to user
        cursor.execute("SELECT user_id FROM Schedules WHERE id = %s", [schedule_id])
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return JsonResponse({"error": "Không có quyền chia sẻ"}, status=403)

        # Get full_name from Users table
        cursor.execute("SELECT full_name FROM Users WHERE id = %s", [user_id])
        user_result = cursor.fetchone()
        if not user_result:
            return JsonResponse({"error": "Người dùng không tồn tại"}, status=404)
        full_name = user_result[0]

        # Check for existing share link
        cursor.execute("SELECT share_link FROM SharedLinks WHERE schedule_id = %s", [schedule_id])
        existing_link = cursor.fetchone()
        if existing_link:
            share_link = existing_link[0]
        else:
            # Generate new share link with lowercase UUID and correct path
            share_token = str(uuid.uuid4()).lower()
            share_link = f"http://{request.get_host()}/recommend/view-schedule/{share_token}/"
            cursor.execute(
                "INSERT INTO SharedLinks (schedule_id, share_link) VALUES (%s, %s)",
                [schedule_id, share_link]
            )
            db.commit()

        # Send email using Gmail SMTP settings from settings.py
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
        if 'db' in locals() and db:
            db.rollback()
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Lỗi không xác định: {str(e)}"}, status=500)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'db' in locals() and db and db.open:
            db.close()


@require_GET
def view_schedule(request, share_token):
    db = None
    cursor = None
    try:
        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )

        cursor = db.cursor()

        # Normalize share_token to lowercase
        share_token = share_token.lower()

        # Construct the expected share_link directly
        share_link_with_slash = f"http://127.0.0.1:8000/recommend/view-schedule/{share_token}/"
        share_link_without_slash = f"http://127.0.0.1:8000/recommend/view-schedule/{share_token}"

        # Case-insensitive lookup
        cursor.execute(
            """
            SELECT schedule_id FROM SharedLinks 
            WHERE LOWER(share_link) = LOWER(%s) OR LOWER(share_link) = LOWER(%s)
            """,
            [share_link_with_slash, share_link_without_slash]
        )
        result = cursor.fetchone()
        if result:
            schedule_id = result[0]
        else:
            return JsonResponse({"error": "Liên kết chia sẻ không hợp lệ"}, status=404)

        # Fetch schedule details
        cursor.execute("SELECT name FROM Schedules WHERE id = %s", [schedule_id])
        schedule = cursor.fetchone()
        if not schedule:
            return JsonResponse({"error": "Lịch trình không tồn tại"}, status=404)

        # Fetch flight details if exists
        cursor.execute("SELECT * FROM Flights WHERE schedule_id = %s", [schedule_id])
        flight = cursor.fetchone()
        flight_data = None
        if flight:
            flight_data = {
                "flight_id": flight[0],
                "departure": flight[1],
                "arrival": flight[2],
                # Add other flight fields as needed
            }

        # Fetch hotel details if exists
        cursor.execute("SELECT * FROM Hotels WHERE schedule_id = %s", [schedule_id])
        hotel = cursor.fetchone()
        hotel_data = None
        if hotel:
            hotel_data = {
                "hotel_id": hotel[0],
                "name": hotel[1],
                "address": hotel[2],
                # Add other hotel fields as needed
            }

        # Fetch days
        cursor.execute("SELECT id, day_index, date_str FROM Days WHERE schedule_id = %s ORDER BY day_index", [schedule_id])
        days = cursor.fetchall()

        # Construct schedule data
        schedule_data = {
            "name": schedule[0],
            "days": []
        }
        for day in days:
            day_id, day_index, date_str = day
            cursor.execute("SELECT * FROM Itineraries WHERE day_id = %s ORDER BY `order`", [day_id])
            itineraries = cursor.fetchall()
            day_plan = {
                "day_index": day_index,
                "date_str": date_str,
                "itineraries": [
                    {
                        "timeslot": item[2],
                        "food_title": item[3],
                        "food_rating": item[4],
                        "food_price": item[5],
                        "food_address": item[6],
                        "food_phone": item[7],
                        "food_link": item[8],
                        "food_image": item[9],
                        "place_title": item[10],
                        "place_rating": item[11],
                        "place_description": item[12],
                        "place_address": item[13],
                        "place_img": item[14],
                        "place_link": item[15],
                        "hotel_name": item[16],
                        "hotel_link": item[17],
                        "hotel_description": item[18],
                        "hotel_price": item[19],
                        "hotel_class": item[20],
                        "hotel_img_origin": item[21],
                        "hotel_location_rating": item[22],
                        "order": item[23]
                    } for item in itineraries
                ]
            }
            schedule_data["days"].append(day_plan)

        # Construct response data
        response_data = {}
        if flight_data:
            response_data["flight"] = flight_data
        if hotel_data:
            response_data["hotel"] = hotel_data
        response_data["schedule"] = schedule_data

        return JsonResponse(response_data, status=200)

    except MySQLdb.Error:
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception:
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi không xác định"}, status=500)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'db' in locals() and db and db.open:
            db.close()


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

        note_activities = data.get("note_activities", "").strip()
        description = data.get("description", "").strip()
        date_activities_str = data.get("date_activities", "").strip()
        status = data.get("status", 0)  # 0: chưa làm, 1: đã làm
        itinerary_id = data.get("itinerary_id")
        date_plan_str = data.get("date_plan",request.session.get('start_day', '')).strip()
        if not note_activities:
            return JsonResponse({"error": "Thiếu trường note_activities"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        # Xử lý date_plan và date_activities
        if itinerary_id:
            # Trường hợp liên kết với itinerary
            cursor.execute("SELECT day_id FROM itineraries WHERE id = %s", [itinerary_id])
            day_id = cursor.fetchone()
            if not day_id:
                cursor.close()
                db.close()
                return JsonResponse({"error": "Itinerary không tồn tại"}, status=404)
            day_id = day_id[0]

            cursor.execute("SELECT schedule_id, date_str FROM days WHERE id = %s", [day_id])
            result = cursor.fetchone()
            if not result:
                cursor.close()
                db.close()
                return JsonResponse({"error": "Ngày không tồn tại"}, status=404)
            schedule_id, date_str = result
            date_activities = date_str

            # Lấy ngày bắt đầu của lịch trình
            cursor.execute("SELECT MIN(date_str) FROM days WHERE schedule_id = %s", [schedule_id])
            start_date = cursor.fetchone()[0]
            date_plan = start_date
        else:
            # Trường hợp độc lập (từ trang chủ hoặc sau khi save plan)
            if date_plan_str:
                # Người dùng nhập date_plan từ trang chủ
                try:
                    date_plan = datetime.strptime(date_plan_str, "%Y-%m-%d").date()
                except ValueError:
                    cursor.close()
                    db.close()
                    return JsonResponse({"error": "Định dạng date_plan không hợp lệ"}, status=400)
            else:
                # Lấy từ session sau khi save plan
                start_day = request.session.get('start_day')
                if not start_day:
                    cursor.close()
                    db.close()
                    return JsonResponse({"error": "Không tìm thấy ngày bắt đầu trong session"}, status=400)
                date_plan = datetime.strptime(start_day, "%Y-%m-%d").date()

            if date_activities_str:
                try:
                    date_activities = datetime.strptime(date_activities_str, "%Y-%m-%d").date()
                except ValueError:
                    cursor.close()
                    db.close()
                    return JsonResponse({"error": "Định dạng date_activities không hợp lệ"}, status=400)
            else:
                date_activities = date_plan  # Mặc định bằng date_plan nếu không cung cấp

        # Chèn dữ liệu vào bảng activities
        cursor.execute(
            """
            INSERT INTO activities (user_id, itinerary_id, note_activities, description, date_activities, status, date_plan)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [user_id, itinerary_id if itinerary_id else None, note_activities, description, date_activities, status, date_plan]
        )
        db.commit()
        activity_id = cursor.lastrowid

        cursor.close()
        db.close()

        return JsonResponse({"message": "Tạo hoạt động thành công", "activity_id": activity_id}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in create_todolist_activity: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

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
            "itinerary_id": row[1],
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


