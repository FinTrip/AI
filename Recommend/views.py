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
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip()
        status = data.get("status", "active").strip()
        role_id = data.get("role_id")

        # Kiểm tra các trường bắt buộc
        if not email or not password or not full_name or not role_id:
            return JsonResponse({"error": "Thiếu các trường bắt buộc: email, password, full_name, role_id"}, status=400)

        # Kiểm tra định dạng email
        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_pattern, email):
            return JsonResponse({"error": "Email không hợp lệ."}, status=400)

        # Kiểm tra status hợp lệ
        valid_statuses = ['active', 'inactive', 'banned']
        if status not in valid_statuses:
            return JsonResponse({"error": "Status phải là 'active', 'inactive', hoặc 'banned'."}, status=400)

        # Ép kiểu role_id thành int
        try:
            role_id = int(role_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Role ID phải là một số nguyên."}, status=400)

        # Kết nối cơ sở dữ liệu
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            # Kiểm tra email đã tồn tại chưa
            cursor.execute("SELECT id FROM Users WHERE email = %s", [email])
            if cursor.fetchone():
                return JsonResponse({"error": "Email đã tồn tại."}, status=400)

            # Kiểm tra role_id có tồn tại không
            cursor.execute("SELECT id FROM Roles WHERE id = %s", [role_id])
            if not cursor.fetchone():
                return JsonResponse({"error": "Role ID không tồn tại."}, status=400)

            # Mã hóa mật khẩu
            hashed_password = hash_password(password)

            # Chèn người dùng mới vào bảng Users
            sql = """
                INSERT INTO Users (email, password, full_name, status, role_id)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, [email, hashed_password, full_name, status, role_id])
            db.commit()

            # Lấy ID của người dùng vừa tạo
            cursor.execute("SELECT LAST_INSERT_ID()")
            user_id = cursor.fetchone()[0]

            return JsonResponse({
                "message": "Tạo người dùng thành công!",
                "user_id": user_id
            }, status=201)

        finally:
            cursor.close()
            db.close()

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
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
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        valid, error = validate_request(data, "email", "password")
        if not valid:
            return JsonResponse({"error": error}, status=400)

        # Kết nối cơ sở dữ liệu
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            # Truy vấn người dùng từ bảng Users
            cursor.execute("SELECT id, password FROM Users WHERE email = %s", [email])
            user = cursor.fetchone()
            if not user:
                return JsonResponse({"error": "Email không tồn tại."}, status=400)

            user_id, hashed_password = user
            if not check_password(password, hashed_password):
                return JsonResponse({"error": "Mật khẩu không đúng."}, status=400)

            request.session['user_id'] = user_id
            request.session.modified = True
            return JsonResponse({"message": "Đăng nhập thành công!", "user_id": user_id}, status=200)

        finally:
            cursor.close()
            db.close()

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
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

        # Lấy province: ưu tiên hotel, sau đó flight, cuối cùng từ input
        province = selected_hotel.get('province', selected_flight.get('destination', data.get("province", "").strip()))

        # Lấy start_day: từ flight hoặc input
        start_day = selected_flight.get('departure_time', data.get("start_day", "").strip())
        if start_day and 'T' in start_day:  # Nếu từ flight, cắt lấy ngày
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

        # Kiểm tra độ dài
        if any(len(value) > 50 for value in [province, start_day, end_day]):
            return JsonResponse({"error": "Dữ liệu đầu vào không được dài quá 50 ký tự."}, status=400)

        # Kiểm tra định dạng province
        province_pattern = r"^[A-Za-z\u00C0-\u1EF9\s]+$"
        if not re.match(province_pattern, province):
            return JsonResponse({"error": "Province chỉ được chứa chữ cái (kể cả có dấu) và khoảng trắng."}, status=400)

        # Kiểm tra định dạng ngày
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(date_pattern, start_day) or not re.match(date_pattern, end_day):
            return JsonResponse({"error": "Định dạng ngày không hợp lệ. Vui lòng sử dụng YYYY-MM-DD."}, status=400)

        fmt = "%Y-%m-%d"
        try:
            start_dt = datetime.strptime(start_day, fmt)
            end_dt = datetime.strptime(end_day, fmt)
        except ValueError:
            return JsonResponse({"error": "Định dạng ngày không hợp lệ. Vui lòng sử dụng YYYY-MM-DD."}, status=400)

        current_date = datetime.now().date()
        if start_dt.date() < current_date or end_dt.date() < current_date:
            return JsonResponse({"error": "Ngày bắt đầu và ngày kết thúc phải không bé hơn ngày hiện tại."}, status=400)

        if start_dt >= end_dt:
            return JsonResponse({"error": "Ngày bắt đầu phải bé hơn ngày kết thúc."}, status=400)

        total_days = (end_dt - start_dt).days + 1
        if total_days > 30:
            return JsonResponse({"error": "Tổng số ngày của lịch trình không được vượt quá 30 ngày."}, status=400)

        # Tải dữ liệu và tạo lịch trình
        food_df, place_df,_ = load_data(FOOD_FILE, PLACE_FILE)
        schedule_result = recommend_trip_schedule(start_day, end_day, province, food_df, place_df)
        if "error" in schedule_result:
            return JsonResponse({"error": schedule_result["error"]}, status=400)

        # Tạo response cơ bản
        response_data = {
            "schedule": schedule_result,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }

        # Thêm từng cái nếu có
        if selected_hotel:
            response_data["hotel"] = selected_hotel
        if selected_flight:
            response_data["flight"] = selected_flight

        return JsonResponse(response_data, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API tìm kiếm khách sạn
@csrf_exempt
@require_POST
def rcm_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        search_term = data.get("destinationInput", "").strip()

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
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"error": "Bạn cần đăng nhập để lưu lịch trình."}, status=403)

        # Kết nối DB và kiểm tra user_id
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            cursor.execute("SELECT id FROM Users WHERE id = %s", [user_id])
            if not cursor.fetchone():
                return JsonResponse({"error": "Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại."}, status=403)

            data = json.loads(request.body)
            schedule_name = data.get("schedule_name", "My Custom Schedule").strip()
            days_data = data.get("days", [])
            province = data.get("destinationInput", "").strip()  # Thêm để hỗ trợ activate

            # Nếu có province từ activate, tự động tạo days_data từ search_province
            if province and not days_data:
                if len(province) > 100:
                    return JsonResponse({"error": "Tỉnh/thành phố không được dài quá 100 ký tự."}, status=400)

                # Tải dữ liệu từ search_province logic
                food_df, place_df,_ = load_data(FOOD_FILE, PLACE_FILE)
                normalized_province = normalize_text(province)

                foods = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')
                places = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)].to_dict('records')

                if not foods and not places:
                    return JsonResponse({"error": "Không tìm thấy hoạt động nào cho tỉnh/thành phố này."}, status=404)

                # Tạo days_data từ foods và places
                days_data = [{
                    "day_index": 1,
                    "date_str": datetime.now().strftime("%Y-%m-%d"),  # Ngày hiện tại làm ví dụ
                    "itinerary": []
                }]

                # Thêm foods vào itinerary
                for food in foods:
                    days_data[0]["itinerary"].append({
                        "timeslot": "morning",  # Mặc định, có thể cải tiến
                        "food": {
                            "province": food.get("province"),
                            "title": food.get("title"),
                            "rating": float(food.get("rating")) if pd.notna(food.get("rating")) else None,
                            "price": food.get("Price"),
                            "address": food.get("address"),
                            "phone": food.get("Phone"),
                            "link": food.get("Link"),
                            "service": food.get("types"),
                            "image": food.get("img")
                        }
                    })

                # Thêm places vào itinerary
                for place in places:
                    days_data[0]["itinerary"].append({
                        "timeslot": "afternoon",  # Mặc định, có thể cải tiến
                        "place": {
                            "province": place.get("province"),
                            "title": place.get("title"),
                            "rating": float(place.get("rating")) if pd.notna(place.get("rating")) else None,
                            "description": place.get("description"),
                            "address": place.get("address"),
                            "img": place.get("img"),
                            "types": place.get("types"),
                            "link": place.get("link")
                        }
                    })

            # Kiểm tra days_data
            if not days_data:
                return JsonResponse({"error": "Dữ liệu ngày không được để trống."}, status=400)

            # Lưu vào DB
            sql_schedule = "INSERT INTO schedule (user_id, name, created_at) VALUES (%s, %s, NOW())"
            cursor.execute(sql_schedule, [user_id, schedule_name])
            schedule_id = cursor.lastrowid

            for day_info in days_data:
                day_index = day_info.get("day_index", 1)
                date_str = day_info.get("date_str", "")
                sql_day = "INSERT INTO day (schedule_id, day_index, date_str) VALUES (%s, %s, %s)"
                cursor.execute(sql_day, [schedule_id, day_index, date_str])
                day_id = cursor.lastrowid

                itinerary_list = day_info.get("itinerary", [])
                order_index = 0
                for item in itinerary_list:
                    timeslot = item.get("timeslot", "")
                    food_data = item.get("food", {}) or {}
                    place_data = item.get("place", {}) or {}
                    hotel_data = item.get("hotel", {}) or {}

                    sql_itinerary = """
                        INSERT INTO itinerary (
                            day_id, timeslot,
                            food_province, food_title, food_rating, food_price, food_address, food_phone, food_link, food_service, food_image,
                            place_province, place_title, place_rating, place_description, place_address, place_img, place_types, place_link,
                            hotel_name, hotel_link, hotel_description, hotel_price, hotel_nearby_place, hotel_class, hotel_img_origin, hotel_location_rating, hotel_province,
                            `order`
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql_itinerary, [
                        day_id, timeslot,
                        food_data.get("province"), food_data.get("title"), food_data.get("rating"), food_data.get("price"),
                        food_data.get("address"), food_data.get("phone"), food_data.get("link"), food_data.get("service"), food_data.get("image"),
                        place_data.get("province"), place_data.get("title"), place_data.get("rating"), place_data.get("description"),
                        place_data.get("address"), place_data.get("img"), str(place_data.get("types")), place_data.get("link"),
                        hotel_data.get("name"), hotel_data.get("link"), hotel_data.get("description"), hotel_data.get("price"),
                        hotel_data.get("name_nearby_place"), hotel_data.get("hotel_class"), hotel_data.get("img_origin"),
                        hotel_data.get("location_rating"), hotel_data.get("province"),
                        order_index
                    ])
                    order_index += 1

            db.commit()

            return JsonResponse({
                "message": "Lịch trình đã được lưu thành công!",
                "schedule_id": schedule_id,
                "timestamp": datetime.now().isoformat(),
                "csrf_token": get_token(request)
            }, status=201)

        finally:
            cursor.close()
            db.close()

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API chia sẻ lịch trình
@csrf_exempt
@require_POST
def share_schedule(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"error": "Bạn cần đăng nhập để chia sẻ lịch trình."}, status=403)

        # Kết nối DB và kiểm tra user_id
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            cursor.execute("SELECT id FROM Users WHERE id = %s", [user_id])
            if not cursor.fetchone():
                return JsonResponse({"error": "Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại."}, status=403)

            data = json.loads(request.body)
            schedule_id = data.get("schedule_id")
            if not schedule_id:
                return JsonResponse({"error": "Thiếu trường schedule_id."}, status=400)

            cursor.execute("SELECT user_id FROM schedule WHERE id = %s", [schedule_id])
            owner = cursor.fetchone()

            if not owner or owner[0] != user_id:
                return JsonResponse({"error": "Bạn không có quyền chia sẻ lịch trình này."}, status=403)

            share_link = f"http://{request.get_host()}/view-schedule/{schedule_id}/"
            cursor.execute(
                "INSERT INTO shared_links (schedule_id, share_link, created_at) VALUES (%s, %s, NOW())",
                [schedule_id, share_link]
            )
            db.commit()

            return JsonResponse({
                "message": "Link chia sẻ đã được tạo và lưu thành công!",
                "share_link": share_link
            }, status=200)

        finally:
            cursor.close()
            db.close()

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API xem lịch trình qua link
@require_GET
def view_schedule(request, schedule_id):
    try:
        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

        try:
            cursor.execute("SELECT name FROM schedule WHERE id = %s", [schedule_id])
            schedule = cursor.fetchone()
            if not schedule:
                return JsonResponse({"error": "Lịch trình không tồn tại."}, status=404)

            cursor.execute("SELECT id, day_index, date_str FROM day WHERE schedule_id = %s ORDER BY day_index", [schedule_id])
            days = cursor.fetchall()

            plan = {"schedule_name": schedule[0], "days": []}
            for day in days:
                day_id, day_index, date_str = day
                cursor.execute("""
                    SELECT timeslot, 
                           food_province, food_title, food_rating, food_price, food_address, food_phone, food_link, food_service, food_image,
                           place_province, place_title, place_rating, place_description, place_address, place_img, place_types, place_link,
                           hotel_name, hotel_link, hotel_description, hotel_price, hotel_nearby_place, hotel_class, hotel_img_origin, hotel_location_rating, hotel_province,
                           `order`
                    FROM itinerary WHERE day_id = %s ORDER BY `order`
                """, [day_id])
                itinerary = cursor.fetchall()
                day_plan = {
                    "day_index": day_index,
                    "date_str": date_str,
                    "itinerary": [
                        {
                            "timeslot": item[0],
                            "food": {
                                "province": item[1], "title": item[2], "rating": item[3], "price": item[4],
                                "address": item[5], "phone": item[6], "link": item[7], "service": item[8], "image": item[9]
                            } if item[2] else None,
                            "place": {
                                "province": item[10], "title": item[11], "rating": item[12], "description": item[13],
                                "address": item[14], "img": item[15], "types": item[16], "link": item[17]
                            } if item[11] else None,
                            "hotel": {
                                "name": item[18], "link": item[19], "description": item[20], "price": item[21],
                                "name_nearby_place": item[22], "hotel_class": item[23], "img_origin": item[24],
                                "location_rating": item[25], "province": item[26]
                            } if item[18] else None,
                            "order": item[27]
                        } for item in itinerary
                    ]
                }
                plan["days"].append(day_plan)

            return JsonResponse({"plan": plan}, status=200)

        finally:
            cursor.close()
            db.close()

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

#selection hotels
@require_POST
def select_hotel(request):
    try:
        data = json.loads(request.body)
        hotel_info = data.get('hotel_info')

        if hotel_info:
            request.session['selected_hotel'] = hotel_info
            return JsonResponse({"message": "Hotel selected successfully"}, status=200)
        else:
            return JsonResponse({"error": "Missing hotel_info"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
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