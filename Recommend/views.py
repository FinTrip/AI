import json,os,re
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from rest_framework import status
from django.conf import settings
import MySQLdb

from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv
from .processed import load_data, recommend_one_day_trip, recommend_trip_schedule, FOOD_FILE, PLACE_FILE

MYSQL_HOST = settings.DATABASES['default']['HOST']
MYSQL_USER = settings.DATABASES['default']['USER']
MYSQL_PASSWORD = settings.DATABASES['default']['PASSWORD']
MYSQL_DB = settings.DATABASES['default']['NAME']
MYSQL_PORT = int(settings.DATABASES['default'].get('PORT', 3306))
MYSQL_CHARSET = 'utf8'

def validate_request(data, *required_fields):
    """Kiểm tra các trường bắt buộc trong request."""
    for field in required_fields:
        if not data.get(field, "").strip():
            return False, f"Thiếu trường bắt buộc: {field}"
    return True, None


# ===================== recommend_travel_day =====================
@csrf_exempt
@require_POST
def recommend_travel_day(request):
    """
    API gợi ý cho 1 ngày: trả về 3 món ăn và 3 địa điểm duy nhất dựa trên province.
    """
    try:
        data = json.loads(request.body)
        location = data.get("location", "").strip()
        if not location:
            return JsonResponse({"error": "Thiếu trường bắt buộc: location"}, status=400)

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
        recommendations = recommend_one_day_trip(location, food_df, place_df)

        return JsonResponse({
            "recommendations": recommendations,
            "location": location,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


# ===================== recommend_travel_schedule =====================
@csrf_exempt
@require_POST
def recommend_travel_schedule(request):
    """
    API gợi ý lịch trình nhiều ngày dựa trên start_day, end_day và province.

    Ràng buộc:
      - start_day và end_day phải theo định dạng YYYY-MM-DD.
      - start_day < end_day.
      - start_day và end_day không được bé hơn ngày hiện tại.
      - Tổng số ngày không vượt quá 30 ngày.
      - Province chỉ được chứa chữ cái và khoảng trắng.
    Nếu vi phạm, trả về JSON lỗi kèm script alert.

    Lịch trình:
      • Ngày đầu tiên (partial): bỏ khung giờ sáng.
            - Noon: 1 món ăn.
            - Afternoon: 1 địa điểm.
            - Evening: 1 món ăn & 1 địa điểm.
      • Ngày cuối cùng (partial): bỏ khung giờ chiều.
            - Morning: 1 món ăn & 1 địa điểm.
            - Noon: 1 món ăn.
            - Evening: 1 món ăn & 1 địa điểm.
      • Các ngày trung gian (full day):
            - Morning: 1 món ăn & 1 địa điểm.
            - Noon: 1 món ăn.
            - Afternoon: 1 địa điểm.
            - Evening: 1 món ăn & 1 địa điểm.
      Mỗi món ăn và mỗi địa điểm chỉ xuất hiện duy nhất trên toàn bộ lịch trình.
    """
    try:
        data = json.loads(request.body)
        start_day = data.get("start_day", "").strip()
        end_day = data.get("end_day", "").strip()
        province = data.get("province", "").strip()

        if not start_day or not end_day or not province:
            return JsonResponse({"error": "Thiếu trường bắt buộc (start_day, end_day, province)"}, status=400)

        # Kiểm tra định dạng ngày
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(date_pattern, start_day) or not re.match(date_pattern, end_day):
            return JsonResponse({"error": "Định dạng ngày không hợp lệ. Vui lòng sử dụng YYYY-MM-DD."}, status=400)

        # Province chỉ chứa chữ cái và khoảng trắng (sau khi chuẩn hóa, unidecode sẽ loại bỏ dấu)
        if not re.match(r"^[a-zA-Z\s]+$", province):
            return JsonResponse({"error": "Province chỉ được chứa chữ cái và khoảng trắng."}, status=400)

        fmt = "%Y-%m-%d"
        try:
            start_dt = datetime.strptime(start_day, fmt)
            end_dt = datetime.strptime(end_day, fmt)
        except ValueError:
            return JsonResponse({"error": "Định dạng ngày không hợp lệ. Vui lòng sử dụng YYYY-MM-DD."}, status=400)

        current_date = datetime.now().date()
        if start_dt.date() < current_date or end_dt.date() < current_date:
            return JsonResponse({
                "error": "Ngày bắt đầu và ngày kết thúc phải không bé hơn ngày hiện tại.",
                "script": "<script>alert('Ngày bắt đầu và ngày kết thúc phải không bé hơn ngày hiện tại!');</script>"
            }, status=400)
        if start_dt >= end_dt:
            return JsonResponse({
                "error": "Ngày bắt đầu phải bé hơn ngày kết thúc.",
                "script": "<script>alert('Ngày bắt đầu phải bé hơn ngày kết thúc!');</script>"
            }, status=400)

        total_days = (end_dt - start_dt).days + 1
        if total_days > 30:
            return JsonResponse({
                "error": "Tổng số ngày của lịch trình không được vượt quá 30 ngày.",
                "script": "<script>alert('Tổng số ngày của lịch trình không được vượt quá 30 ngày!');</script>"
            }, status=400)

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
        schedule_result = recommend_trip_schedule(start_day, end_day, province, food_df, place_df)
        if "error" in schedule_result:
            return JsonResponse({"error": schedule_result["error"]}, status=400)

        return JsonResponse({
            "schedule": schedule_result,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


# ===================== Endpoint: Save Schedule =====================
@csrf_exempt
@require_POST
def save_schedule(request):
    """
    Lưu lịch trình (schedule) do người dùng chỉnh sửa vào MySQL bằng raw SQL.

    Dữ liệu gửi lên có dạng:
    {
      "user_id": 1,
      "schedule_name": "Lịch đi Quảng Nam",
      "flight": {
          "outbound_flight_code": "VN123",
          "outbound_time": "2025-04-01T08:00:00",
          "total_price_vnd": 5000000,
          "base_price_vnd": 4500000,
          "fare_basis": "Y",
          "cabin": "Economy"
      },
      "hotel": {
          "name": "Hotel ABC",
          "link": "http://hotelabc.com",
          "description": "Luxury hotel",
          "price": 1200000,
          "name_nearby_place": "City Center",
          "hotel_class": "5-star",
          "img_origin": ["img1.jpg", "img2.jpg"],
          "location_rating": 4.8
      },
      "days": [
        {
          "day_index": 1,
          "date_str": "2025-04-01",
          "itinerary": [
            {
              "timeslot": "noon",
              "food": {"title": "Mì Quảng", "address": "95 Lê Lợi"},
              "place": {}
            },
            {
              "timeslot": "afternoon",
              "food": {},
              "place": {"title": "Hội An", "address": "Phố cổ Hội An"}
            },
            {
              "timeslot": "evening",
              "food": {"title": "Cao Lầu", "address": "12 Nguyễn Thái Học"},
              "place": {"title": "Cafe", "address": "Đường Trần Phú"}
            }
          ]
        },
        // Các ngày khác...
      ]
    }

    Ràng buộc:
      - Nếu một số trường như food, place, title, address không có, lưu NULL hoặc để trống.
      - Flight và hotel là tùy chọn; nếu không có, lưu giá trị NULL.
    """
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        schedule_name = data.get("schedule_name", "My Custom Schedule")
        days_data = data.get("days")
        flight_info = data.get("flight")  # dict hoặc None
        hotel_info = data.get("hotel")  # dict hoặc None

        if days_data is None or not isinstance(days_data, list):
            return JsonResponse({"error": "Trường 'days' phải là danh sách."}, status=400)

        # Validate cấu trúc của mỗi ngày
        for day in days_data:
            if not isinstance(day, dict):
                return JsonResponse({"error": "Mỗi mục trong 'days' phải là đối tượng JSON."}, status=400)
            if "day_index" in day:
                try:
                    int(day["day_index"])
                except (ValueError, TypeError):
                    return JsonResponse({"error": "'day_index' phải là số nguyên."}, status=400)
            if "date_str" in day and day["date_str"]:
                try:
                    datetime.strptime(day["date_str"], "%Y-%m-%d")
                except ValueError:
                    return JsonResponse({"error": "'date_str' phải theo định dạng YYYY-MM-DD."}, status=400)
            if "itinerary" in day and not isinstance(day["itinerary"], list):
                return JsonResponse({"error": "'itinerary' phải là một danh sách."}, status=400)

        # Kết nối đến MySQL sử dụng thông số từ settings.py
        db = MySQLdb.connect(
            host=settings.DATABASES['default']['HOST'],
            user=settings.DATABASES['default']['USER'],
            passwd=settings.DATABASES['default']['PASSWORD'],
            db=settings.DATABASES['default']['NAME'],
            port=int(settings.DATABASES['default'].get('PORT', 3306)),
            charset='utf8'
        )
        cursor = db.cursor()

        # INSERT vào bảng schedule, lưu flight_info và hotel_info dưới dạng JSON
        sql_schedule = """
            INSERT INTO schedule (user_id, name, flight_info, hotel_info, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """
        flight_json = json.dumps(flight_info) if flight_info else None
        hotel_json = json.dumps(hotel_info) if hotel_info else None
        cursor.execute(sql_schedule, [user_id, schedule_name, flight_json, hotel_json])
        schedule_id = cursor.lastrowid

        # Lưu từng ngày
        for day_info in days_data:
            day_index = day_info.get("day_index", 1)
            date_str = day_info.get("date_str", "")
            sql_day = """
                INSERT INTO day (schedule_id, day_index, date_str)
                VALUES (%s, %s, %s)
            """
            cursor.execute(sql_day, [schedule_id, day_index, date_str])
            day_id = cursor.lastrowid

            # Lưu từng timeslot trong itinerary
            itinerary_list = day_info.get("itinerary", [])
            order_index = 0
            for item in itinerary_list:
                timeslot = item.get("timeslot", "")
                food_data = item.get("food", {})
                place_data = item.get("place", {})

                food_title = food_data.get("title")
                food_address = food_data.get("address")
                place_title = place_data.get("title")
                place_address = place_data.get("address")

                sql_itinerary = """
                    INSERT INTO itinerary
                    (day_id, timeslot, food_title, food_address, place_title, place_address, `order`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql_itinerary, [
                    day_id,
                    timeslot,
                    food_title,
                    food_address,
                    place_title,
                    place_address,
                    order_index
                ])
                order_index += 1

        db.commit()
        cursor.close()
        db.close()

        return JsonResponse({
            "message": "Schedule saved successfully!",
            "schedule_id": schedule_id,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=201)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


# ===================== Endpoint: Flight Search =====================
@csrf_exempt
@require_POST
def rcm_flight(request):
    """
    Endpoint để tìm kiếm vé máy bay.

    Nếu dữ liệu gửi lên có trường "action": "select",
    nghĩa là người dùng đã chọn vé phù hợp và muốn chuyển sang lịch trình.

    Dữ liệu gửi lên (cho tìm kiếm):
    {
        "origin": "Hanoi",
        "destination": "Ho Chi Minh",
        "departure_date": "2025-04-01"
    }

    Dữ liệu gửi lên (cho lựa chọn):
    {
        "action": "select",
        "flight": {
            "outbound_flight_code": "VN123",
            "outbound_time": "2025-04-01T08:00:00",
            "total_price_vnd": 5000000,
            "base_price_vnd": 4500000,
            "fare_basis": "Y",
            "cabin": "Economy"
        }
    }
    """
    try:
        if request.content_type != "application/json":
            return JsonResponse({"error": "Invalid content type. JSON required!"}, status=400)

        data = json.loads(request.body)
        action = data.get("action", "").strip().lower()

        if action == "select":
            selected_flight = data.get("flight")
            if not selected_flight:
                return JsonResponse({"error": "Missing flight details for selection."}, status=400)
            return JsonResponse({
                "message": "Flight selected. Redirecting to schedule.",
                "selected_flight": selected_flight,
                "redirect_url": "/schedule/"  # Ví dụ URL chuyển tiếp
            }, status=200)

        origin = data.get("origin", "").strip()
        destination = data.get("destination", "").strip()
        departure_date = data.get("departure_date", "").strip()

        if not origin or not destination or not departure_date:
            return JsonResponse({"error": "Missing required input fields!"}, status=400)

        if any(len(value) > 50 for value in [origin, destination, departure_date]):
            return JsonResponse({"error": "Input values are too long!"}, status=400)

        if any(char in origin + destination for char in "<>\"'{}[]()|&;"):
            return JsonResponse({"error": "Invalid characters in input!"}, status=400)

        # Giả sử search_flight_service được định nghĩa để trả về danh sách vé máy bay
        result = search_flight_service(origin, destination, departure_date)
        return JsonResponse(result, safe=False, status=200 if "error" not in result else 500)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format!"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ===================== Endpoint: Hotel Search =====================
@csrf_exempt
@require_POST
def rcm_hotel(request):
    """
    Endpoint để tìm kiếm khách sạn.

    Nếu có trường "action": "select" trong request, nghĩa là người dùng đã chọn khách sạn phù hợp và muốn chuyển sang lịch trình.

    Dữ liệu gửi lên (cho tìm kiếm):
    {
        "province": "Hanoi"
    }

    Dữ liệu gửi lên (cho lựa chọn):
    {
        "action": "select",
        "hotel": {
            "name": "Hotel ABC",
            "link": "http://hotelabc.com",
            "description": "Luxury hotel",
            "price": 1200000,
            "name_nearby_place": "City Center",
            "hotel_class": "5-star",
            "img_origin": ["img1.jpg", "img2.jpg"],
            "location_rating": 4.8
        }
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        action = data.get("action", "").strip().lower()

        if action == "select":
            selected_hotel = data.get("hotel")
            if not selected_hotel:
                return JsonResponse({"error": "Missing hotel details for selection."}, status=400)
            return JsonResponse({
                "message": "Hotel selected. Redirecting to schedule.",
                "selected_hotel": selected_hotel,
                "redirect_url": "/schedule/"  # Ví dụ URL chuyển tiếp
            }, status=200)

        search_term = data.get("province", "").strip()
        if not search_term:
            return JsonResponse({"error": "Please provide a province or a nearby place.", "status": 400}, status=400)

        # Giả sử process_hotel_data_from_csv được định nghĩa để trả về danh sách khách sạn từ CSV
        result = process_hotel_data_from_csv(search_term)
        return JsonResponse(
            {"hotels": result} if result else {"error": "No hotels found.", "status": 404},
            json_dumps_params={"ensure_ascii": False},
            status=200 if result else 404
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data.", "status": 400}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"System error: {str(e)}", "status": 500}, status=500)