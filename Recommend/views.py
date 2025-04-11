import json
import os
import re
import pandas as pd
import traceback
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from rest_framework import status
from django.conf import settings
import MySQLdb
import jwt
import bcrypt

from .CheckException import validate_request
from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv,update_hotel_in_csv, delete_hotel_in_csv,show_hotel_in_csv, get_hotel_homepage
from .processed import load_data, recommend_one_day_trip, recommend_trip_schedule, FOOD_FILE, PLACE_FILE,HOTEL_FILE,normalize_text,get_food_homepage,get_place_homepage,get_city_to_be_miss
from .weather import display_forecast, get_weather

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
            return JsonResponse({"error": "Role ID không tồn tại"}, status=400)

        # Kiểm tra email trùng lặp
        cursor.execute("SELECT id FROM Users WHERE email = %s", [email])
        if cursor.fetchone():
            return JsonResponse({"error": "Email đã tồn tại"}, status=400)

        hashed_password = hash_password(password)
        # Không cần chèn created_at, updated_at vì cơ sở dữ liệu tự xử lý
        cursor.execute(
            "INSERT INTO Users (email, password, full_name, status, role_id) VALUES (%s, %s, %s, %s, %s)",
            [email, hashed_password, full_name, status, int(role_id)]
        )
        db.commit()
        user_id = cursor.lastrowid

        cursor.close()
        db.close()
        return JsonResponse({"message": "Tạo người dùng thành công", "user_id": user_id}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

#hàm delete
@csrf_exempt
@require_POST
def delete_user(request):
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        # Kiểm tra trường bắt buộc
        if not user_id:
            return JsonResponse({"error": "Thiếu trường bắt buộc: user_id"}, status=400)

        # Ép kiểu user_id thành int
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "User ID phải là một số nguyên."}, status=400)

        # Kết nối cơ sở dữ liệu
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            # Kiểm tra người dùng có tồn tại không
            cursor.execute("SELECT id FROM Users WHERE id = %s", [user_id])
            if not cursor.fetchone():
                return JsonResponse({"error": "Người dùng không tồn tại."}, status=404)

            # Xóa người dùng
            cursor.execute("DELETE FROM Users WHERE id = %s", [user_id])
            db.commit()

            return JsonResponse({
                "message": "Xóa người dùng thành công!",
                "user_id": user_id
            }, status=200)

        finally:
            cursor.close()
            db.close()

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_POST
def update_user(request):
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")

        # Kiểm tra trường bắt buộc
        if not user_id:
            return JsonResponse({"error": "Thiếu trường bắt buộc: user_id"}, status=400)

        # Ép kiểu user_id thành int
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "User ID phải là một số nguyên."}, status=400)

        # Lấy các trường cần cập nhật (các trường không bắt buộc)
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip()
        status = data.get("status", "").strip()
        role_id = data.get("role_id")

        # Kết nối cơ sở dữ liệu
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            # Kiểm tra người dùng có tồn tại không
            cursor.execute("SELECT email, password, full_name, status, role_id FROM Users WHERE id = %s", [user_id])
            user = cursor.fetchone()
            if not user:
                return JsonResponse({"error": "Người dùng không tồn tại."}, status=404)

            # Lấy thông tin hiện tại của người dùng
            current_email, current_password, current_full_name, current_status, current_role_id = user

            # Kiểm tra và cập nhật email (nếu có)
            if email:
                email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
                if not re.match(email_pattern, email):
                    return JsonResponse({"error": "Email không hợp lệ."}, status=400)
                # Kiểm tra email đã tồn tại chưa (trừ email của chính user này)
                cursor.execute("SELECT id FROM Users WHERE email = %s AND id != %s", [email, user_id])
                if cursor.fetchone():
                    return JsonResponse({"error": "Email đã tồn tại."}, status=400)
            else:
                email = current_email

            # Kiểm tra và mã hóa mật khẩu (nếu có)
            if password:
                hashed_password = hash_password(password)
            else:
                hashed_password = current_password

            # Kiểm tra và cập nhật full_name (nếu có)
            if not full_name:
                full_name = current_full_name

            # Kiểm tra và cập nhật status (nếu có)
            if status:
                valid_statuses = ['active', 'inactive', 'banned']
                if status not in valid_statuses:
                    return JsonResponse({"error": "Status phải là 'active', 'inactive', hoặc 'banned'."}, status=400)
            else:
                status = current_status

            # Kiểm tra và cập nhật role_id (nếu có)
            if role_id is not None:
                try:
                    role_id = int(role_id)
                    cursor.execute("SELECT id FROM Roles WHERE id = %s", [role_id])
                    if not cursor.fetchone():
                        return JsonResponse({"error": "Role ID không tồn tại."}, status=400)
                except (TypeError, ValueError):
                    return JsonResponse({"error": "Role ID phải là một số nguyên."}, status=400)
            else:
                role_id = current_role_id

            # Cập nhật thông tin người dùng
            sql = """
                UPDATE Users 
                SET email = %s, password = %s, full_name = %s, status = %s, role_id = %s
                WHERE id = %s
            """
            cursor.execute(sql, [email, hashed_password, full_name, status, role_id, user_id])
            db.commit()

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

        finally:
            cursor.close()
            db.close()

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_POST
def login_user(request):
    """Đăng nhập người dùng."""
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()

        if not email or not password:
            return JsonResponse({"error": "Thiếu email hoặc password"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()
        cursor.execute("SELECT id, password FROM Users WHERE email = %s", [email])
        user = cursor.fetchone()

        if not user or not check_password(password, user[1]):
            return JsonResponse({"error": "Email hoặc mật khẩu không đúng"}, status=400)

        request.session['user_id'] = user[0]
        cursor.close()
        db.close()
        return JsonResponse({"message": "Đăng nhập thành công", "user_id": user[0]}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
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

        # Kiểm tra độ dài location
        if len(location) > 100:
            return JsonResponse({"error": "Location không được dài quá 100 ký tự."}, status=400)

        food_df, place_df,_ = load_data(FOOD_FILE, PLACE_FILE)
        recommendations = recommend_one_day_trip(location, food_df, place_df)
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
        return JsonResponse({"error": str(e)}, status=500)

# API gợi ý lịch trình nhiều ngày
@csrf_exempt
@require_POST
def recommend_travel_schedule(request):
    try:
        data = json.loads(request.body)
        selected_hotel = request.session.get('selected_hotel', {})
        selected_flight = request.session.get('selected_flight', {})
        selected_place = request.session.get('selected_province',{})
        selected_place_detail = request.session.get('selected_place_info',{})

        # Lấy province: ưu tiên place hotel, sau đó flight, cuối cùng từ input
        province = (
                selected_place or
                selected_hotel.get('province') or
                selected_flight.get('destination') or
                data.get("province", "").strip()
        )

        # Lấy start_day: từ flight hoặc input
        start_day = selected_flight.get('departure_time', data.get("start_day", "").strip())
        if start_day and 'T' in start_day:
            start_day = start_day.split('T')[0]

        # Lấy end_day: luôn từ input
        end_day = data.get("end_day", "").strip()

        # Kiểm tra các trường bắt buộc
        missing_fields = []
        if not province:
            missing_fields.append("province")
        if not start_day:
            missing_fields.append("start_day")
        if not end_day:
            missing_fields.append("end_day")
        if missing_fields:
            return JsonResponse({"error": f"Thiếu trường bắt buộc: {', '.join(missing_fields)}"}, status=400)

        # Kiểm tra độ dài của các trường đầu vào
        if any(len(value) > 50 for value in [province, start_day, end_day]):
            return JsonResponse({"error": "Dữ liệu đầu vào không được dài quá 50 ký tự."}, status=400)

        # Kiểm tra định dạng province (cho phép chữ cái và khoảng trắng)
        province_pattern = r"^[A-Za-z\u00C0-\u1EF9\s]+$"
        if not re.match(province_pattern, province):
            return JsonResponse({"error": "Province chỉ được chứa chữ cái (kể cả có dấu) và khoảng trắng."}, status=400)

        # Kiểm tra định dạng ngày (YYYY-MM-DD)
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(date_pattern, start_day) or not re.match(date_pattern, end_day):
            return JsonResponse({"error": "Định dạng ngày không hợp lệ. Vui lòng sử dụng YYYY-MM-DD."}, status=400)

        fmt = "%Y-%m-%d"
        try:
            start_date = datetime.strptime(start_day, fmt).date()
            end_date = datetime.strptime(end_day, fmt).date()
        except ValueError:
            return JsonResponse({"error": "Định dạng ngày không hợp lệ. Vui lòng sử dụng YYYY-MM-DD."}, status=400)

        current_date = datetime.now().date()
        if start_date < current_date or end_date < current_date:
            return JsonResponse({"error": "Ngày bắt đầu và ngày kết thúc phải không bé hơn ngày hiện tại."}, status=400)

        if start_date >= end_date:
            return JsonResponse({"error": "Ngày bắt đầu phải bé hơn ngày kết thúc."}, status=400)

        total_days = (end_date - start_date).days + 1
        if total_days > 30:
            return JsonResponse({"error": "Tổng số ngày của lịch trình không được vượt quá 30 ngày."}, status=400)

        # Tải dữ liệu và tạo lịch trình (giả sử hàm này đã được định nghĩa)
        food_df, place_df, _ = load_data(FOOD_FILE, PLACE_FILE)
        schedule_result = recommend_trip_schedule(start_day, end_day, province, food_df, place_df)
        if "error" in schedule_result:
            return JsonResponse({"error": schedule_result["error"]}, status=400)

        response_data = {
            "schedule": schedule_result,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }

        if total_days < 14:
            offset = (start_date - current_date).days
            required_forecast_days = offset + total_days
            weather_data = get_weather(province, forecast_days=required_forecast_days)
            weather_forecast = display_forecast(weather_data, start_day=offset, end_day=offset + total_days)
            response_data["weather_forecast"] = weather_forecast
        else:
            response_data["weather_forecast"] = "Bỏ qua do lịch trình vượt quá giới hạn thời tiết (>= 14 ngày)."

        # Thêm thông tin hotel và flight nếu có
        if selected_hotel:
            response_data["hotel"] = selected_hotel
        if selected_flight:
            response_data["flight"] = selected_flight

        if selected_place_detail:
            response_data["place"] = selected_place_detail

        return JsonResponse(response_data, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


####Admin
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@csrf_exempt
@require_POST
def update_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        hotel_name = data.get("name", "").strip()

        if not hotel_name:
            return JsonResponse({"error": "Vui lòng cung cấp tên khách sạn (name)."}, status=400)

        # Các trường có thể cập nhật
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

        # Gọi hàm cập nhật trong file CSV
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

@csrf_exempt
@require_POST
def delete_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        hotel_name = data.get("name", "").strip()

        if not hotel_name:
            return JsonResponse({"error": "Vui lòng cung cấp tên khách sạn (name)."}, status=400)

        # Gọi hàm xóa trong file CSV
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)
### end admin



#search province
@csrf_exempt
@require_POST
def search_province(request):
    try:
        # Kiểm tra xem request.body có rỗng không
        if not request.body:
            return JsonResponse({"error": "Không có dữ liệu trong request body."}, status=400)

        # Parse dữ liệu từ request body
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError as e:
            return JsonResponse({"error": f"Dữ liệu JSON không hợp lệ: {str(e)}"}, status=400)

        province = data.get("destinationInput", "").strip()
        query = data.get("query", "").strip()

        # Kiểm tra province
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)
        if len(province) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        # Tải dữ liệu
        food_df, place_df, hotel_df = load_data(FOOD_FILE, PLACE_FILE, HOTEL_FILE)

        # Chuẩn hóa đầu vào
        normalized_province = normalize_text(province)
        normalized_query = normalize_text(query) if query else None

        # Hàm lọc dữ liệu
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

        # Lọc dữ liệu
        filtered_food = filter_data(food_df, province_col='province', name_col='title')
        filtered_place = filter_data(place_df, province_col='province', name_col='title')
        filtered_hotel = filter_data(hotel_df, province_col='province', name_col='name')

        # Chuyển đổi dữ liệu thành danh sách dictionary
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

        # Kiểm tra nếu không tìm thấy kết quả
        if not food_list and not place_list and not hotel_list:
            return JsonResponse({"error": "Không tìm thấy hoạt động nào cho tỉnh/thành phố này."}, status=404)

        # Trả về phản hồi JSON
        return JsonResponse({
            "foods": food_list,
            "places": place_list,
            "hotels": hotel_list,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

#Những Thành Phố Không Thể Bỏ Lỡ
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)


#search place
@csrf_exempt
@require_POST
def search_place(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        province = data.get("destinationInput", "").strip()
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        # Kiểm tra độ dài
        if len(province) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        # Tải dữ liệu
        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)

        # Chuẩn hóa tỉnh/thành phố đầu vào
        normalized_province = normalize_text(province)

        # Lọc dữ liệu theo tỉnh/thành phố
        foods = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')
        places = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')

        place_list = [{
            "province": place.get("province"),
            "title": place.get("title"),
            "rating": float(place.get("rating")) if pd.notna(place.get("rating")) else None,
            "description": place.get("description"),
            "address": place.get("address"),
            "img": place.get("img"),
            "types": place.get("types"),
            "link": place.get("link")  # Cột này có thể không tồn tại
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

#search province
@csrf_exempt
@require_POST
def search_food(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        province = data.get("destinationInput", "").strip()
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        # Kiểm tra độ dài
        if len(province) > 100:
            return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

        # Tải dữ liệu
        food_df, place_df,_ = load_data(FOOD_FILE, PLACE_FILE)

        # Chuẩn hóa tỉnh/thành phố đầu vào
        normalized_province = normalize_text(province)

        # Lọc dữ liệu theo tỉnh/thành phố
        foods = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')
        places = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')

        # Chuyển đổi dữ liệu thành định dạng JSON
        food_list = [{
            "province": food.get("province"),
            "title": food.get("title"),
            "rating": float(food.get("rating")) if pd.notna(food.get("rating")) else None,
            "price": food.get("Price"),  # Cột này có thể không tồn tại
            "address": food.get("address"),
            "phone": food.get("Phone"),  # Cột này có thể không tồn tại
            "link": food.get("Link"),    # Cột này có thể không tồn tại
            "service": food.get("types"),  # Đã đổi từ 'Service' thành 'types' trong load_data
            "image": food.get("img")
        } for food in foods]

        if not food_list :
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)

# API lưu lịch trình
@csrf_exempt
@require_POST
def save_schedule(request):
    """Lưu lịch trình vào bảng Schedules, Days, Itineraries."""
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"error": "Cần đăng nhập"}, status=403)

        data = json.loads(request.body)
        schedule_name = data.get("schedule_name", "My Schedule").strip()
        days_data = data.get("days", [])

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        # Lưu vào Schedules, không cần chèn created_at
        cursor.execute("INSERT INTO Schedules (user_id, name) VALUES (%s, %s)", [user_id, schedule_name])
        schedule_id = cursor.lastrowid

        for day in days_data:
            day_index = day.get("day_index", 1)
            date_str = day.get("date_str", "")
            cursor.execute("INSERT INTO Days (schedule_id, day_index, date_str) VALUES (%s, %s, %s)",
                           [schedule_id, day_index, date_str])
            day_id = cursor.lastrowid

            itinerary_list = day.get("itinerary", [])
            for item in itinerary_list:
                cursor.execute(
                    "INSERT INTO Itineraries (day_id, timeslot, food_title, food_rating, food_price, food_address, food_phone, food_link, food_image, place_title, place_rating, place_description, place_address, place_img, place_link, hotel_name, hotel_link, hotel_description, hotel_price, hotel_class, hotel_img_origin, hotel_location_rating, `order`) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [day_id, item.get("timeslot"), item.get("food_title"), item.get("food_rating"), item.get("food_price"), item.get("food_address"), item.get("food_phone"), item.get("food_link"), item.get("food_image"), item.get("place_title"), item.get("place_rating"), item.get("place_description"), item.get("place_address"), item.get("place_img"), item.get("place_link"), item.get("hotel_name"), item.get("hotel_link"), item.get("hotel_description"), item.get("hotel_price"), item.get("hotel_class"), item.get("hotel_img_origin"), item.get("hotel_location_rating"), item.get("order")]
                )

        db.commit()
        cursor.close()
        db.close()
        return JsonResponse({"message": "Lưu thành công", "schedule_id": schedule_id}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API chia sẻ lịch trình
@csrf_exempt
@require_POST
def share_schedule(request):
    """Chia sẻ lịch trình và lưu link vào SharedLinks."""
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"error": "Cần đăng nhập"}, status=403)

        data = json.loads(request.body)
        schedule_id = data.get("schedule_id")
        if not schedule_id:
            return JsonResponse({"error": "Thiếu schedule_id"}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()
        cursor.execute("SELECT user_id FROM Schedules WHERE id = %s", [schedule_id])
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return JsonResponse({"error": "Không có quyền chia sẻ"}, status=403)

        share_link = f"http://{request.get_host()}/view-schedule/{schedule_id}/"
        cursor.execute("INSERT INTO SharedLinks (schedule_id, share_link) VALUES (%s, %s)",
                       [schedule_id, share_link])
        db.commit()
        cursor.close()
        db.close()
        return JsonResponse({"message": "Chia sẻ thành công", "share_link": share_link}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API xem lịch trình qua link
@require_GET
def view_schedule(request, schedule_id):
    """Xem lịch trình qua link."""
    try:
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()
        cursor.execute("SELECT name FROM Schedules WHERE id = %s", [schedule_id])
        schedule = cursor.fetchone()
        if not schedule:
            return JsonResponse({"error": "Lịch trình không tồn tại"}, status=404)

        cursor.execute("SELECT id, day_index, date_str FROM Days WHERE schedule_id = %s ORDER BY day_index", [schedule_id])
        days = cursor.fetchall()

        plan = {"schedule_name": schedule[0], "days": []}
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
            plan["days"].append(day_plan)

        cursor.close()
        db.close()
        return JsonResponse({"plan": plan}, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API tìm kiếm chuyến bay
@csrf_exempt
@require_POST
def rcm_flight(request):
    try:
        data = json.loads(request.body)
        origin = data.get("origin", "").strip()
        destination = data.get("destination", "").strip()
        departure_date = data.get("departure_date", "").strip()

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
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_POST
def select_flight(request):
    try:
        data = json.loads(request.body)
        flight_info = data.get('flight_info')

        if not flight_info:
            return JsonResponse({"error": "Missing flight info"},status=400)

        request.session['selected_flight'] = {
            'flight_details': flight_info,
            'origin': flight_info.get('origin', 'N/A'),
            'destination': flight_info.get('destination', 'N/A'),
            'departure_time': flight_info.get('departure_time', 'N/A')
        }
        return JsonResponse({"error": "Flight selected successful"},status=200)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": f"Error system {str(e)}"}, status=400)



# API tìm kiếm khách sạn
@csrf_exempt
@require_POST
def rcm_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        search_term = data.get("destination", "").strip()

        if not search_term:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        # Kiểm tra độ dài
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
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)



#selection hotels
@csrf_exempt
@require_POST
def select_hotel(request):
    try:
        data = json.loads(request.body)
        hotel_info = data.get('hotel_info')

        if hotel_info:
            request.session['selected_hotel'] = {
                'hotel_details' : hotel_info,
                'destination': hotel_info.get('destination', 'N/A'),
            }
            return JsonResponse({"message": "Hotel selected successfully"}, status=200)
        else:
            return JsonResponse({"error": "Missing hotel_info"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)


#Homepage
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
        return JsonResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status=500)