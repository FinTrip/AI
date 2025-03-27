import json
import os
import re
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

from .CheckException import validate_request, check_password
from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv
from .processed import load_data, recommend_one_day_trip, recommend_trip_schedule, FOOD_FILE, PLACE_FILE, search_place

# Cấu hình MySQL từ settings.py
MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'

# API đăng nhập người dùng (sửa để dùng email thay vì username)
@csrf_exempt
@require_POST
def login_user(request):
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip()  # Sửa từ username thành email
        password = data.get("password", "").strip()
        valid, error = validate_request(data, "email", "password")  # Cập nhật trường kiểm tra
        if not valid:
            return JsonResponse({"error": error}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()
        cursor.execute("SELECT id, password FROM user WHERE email = %s", [email])  # Sửa từ username thành email
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if not user:
            return JsonResponse({"error": "Email không tồn tại."}, status=400)  # Cập nhật thông báo lỗi

        user_id, hashed_password = user
        if not check_password(password, hashed_password):
            return JsonResponse({"error": "Mật khẩu không đúng."}, status=400)

        request.session['user_id'] = user_id
        return JsonResponse({"message": "Đăng nhập thành công!", "user_id": user_id}, status=200)

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

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
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
        start_day = data.get("start_day", "").strip()
        end_day = data.get("end_day", "").strip()
        province = data.get("province", "").strip()

        if not start_day or not end_day or not province:
            return JsonResponse({"error": "Thiếu trường bắt buộc: start_day, end_day, province"}, status=400)

        province_pattern = r"^[A-Za-z\u00C0-\u1EF9\s]+$"
        if not re.match(province_pattern, province):
            return JsonResponse({"error": "Province chỉ được chứa chữ cái (kể cả có dấu) và khoảng trắng."}, status=400)

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

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
        schedule_result = recommend_trip_schedule(start_day, end_day, province, food_df, place_df)
        if "error" in schedule_result:
            return JsonResponse({"error": schedule_result["error"]}, status=400)

        return JsonResponse({
            "schedule": schedule_result,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

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

# API tìm kiếm hoạt động (food và place)
@csrf_exempt
@require_POST
def search_province(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        province = data.get("destinationInput", "").strip()
        if not province:
            return JsonResponse({"error": "Vui lòng cung cấp tỉnh/thành phố."}, status=400)

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
        foods = food_df[food_df['Province'].str.contains(province, case=False, na=False)].to_dict('records')
        places = place_df[place_df['Province'].str.contains(province, case=False, na=False)].to_dict('records')

        food_list = [{
            "province": food.get("Province"),
            "title": food.get("Title"),
            "rating": food.get("Rating"),
            "price": food.get("Price"),
            "address": food.get("Address"),
            "phone": food.get("Phone"),
            "link": food.get("Link"),
            "service": food.get("Service"),
            "image": food.get("Image")
        } for food in foods]

        place_list = [{
            "province": place.get("Province"),
            "title": place.get("Title"),
            "rating": place.get("Rating"),
            "description": place.get("Description"),
            "address": place.get("Address"),
            "img": place.get("Img"),
            "types": place.get("Types"),
            "link": place.get("Link")
        } for place in places]

        if not food_list and not place_list:
            return JsonResponse({"error": "Không tìm thấy hoạt động nào cho tỉnh/thành phố này."}, status=404)

        return JsonResponse({
            "foods": food_list,
            "places": place_list,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

# API lưu lịch trình
@csrf_exempt
@require_POST
def save_schedule(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"error": "Bạn cần đăng nhập để lưu lịch trình."}, status=403)

        data = json.loads(request.body)
        schedule_name = data.get("schedule_name", "My Custom Schedule").strip()
        days_data = data.get("days", [])

        if not days_data:
            return JsonResponse({"error": "Dữ liệu ngày không được để trống."}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()

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
        cursor.close()
        db.close()

        return JsonResponse({
            "message": "Lịch trình đã được lưu thành công!",
            "schedule_id": schedule_id,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=201)

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

        data = json.loads(request.body)
        schedule_id = data.get("schedule_id")
        if not schedule_id:
            return JsonResponse({"error": "Thiếu trường schedule_id."}, status=400)

        db = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD,
                             db=MYSQL_DB, port=MYSQL_PORT, charset=MYSQL_CHARSET)
        cursor = db.cursor()
        cursor.execute("SELECT user_id FROM schedule WHERE id = %s", [schedule_id])
        owner = cursor.fetchone()
        cursor.close()
        db.close()

        if not owner or owner[0] != user_id:
            return JsonResponse({"error": "Bạn không có quyền chia sẻ lịch trình này."}, status=403)

        share_link = f"/view-schedule/{schedule_id}/"  # Sửa để khớp với URL trong urls.py
        return JsonResponse({"share_link": share_link}, status=200)

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