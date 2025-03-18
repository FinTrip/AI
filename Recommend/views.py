import json,os
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from rest_framework import status


from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv
from .processed import load_data, recommend_one_day_trip, recommend_trip_schedule, FOOD_FILE, PLACE_FILE


def validate_request(data, *required_fields):
    """Kiểm tra các trường bắt buộc trong request."""
    for field in required_fields:
        if not data.get(field, "").strip():
            return False, f"Thiếu trường bắt buộc: {field}"
    return True, None


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


@csrf_exempt
@require_POST
def recommend_travel_schedule(request):
    """
    API gợi ý lịch trình nhiều ngày dựa trên start_day, end_day và province.
    Ràng buộc:
      - start_day và end_day phải theo định dạng YYYY-MM-DD.
      - start_day < end_day.
      - start_day và end_day không được bé hơn ngày hiện tại.
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
    Mỗi món ăn và địa điểm chỉ xuất hiện 1 lần trên toàn bộ lịch trình.
    """
    try:
        data = json.loads(request.body)
        start_day = data.get("start_day", "").strip()
        end_day = data.get("end_day", "").strip()
        province = data.get("province", "").strip()
        if not start_day or not end_day or not province:
            return JsonResponse({"error": "Thiếu trường bắt buộc (start_day, end_day, province)"}, status=400)

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


@csrf_exempt
@require_POST
def rcm_flight(request):
    """Endpoint to search for flights."""
    if request.method == 'POST':
        try:
            if request.content_type != "application/json":
                return JsonResponse({"error": "Invalid content type. JSON required!"}, status=400)

            data = json.loads(request.body)
            origin = data.get("origin", "").strip()
            destination = data.get("destination", "").strip()
            departure_date = data.get("departure_date", "").strip()

            if not origin or not destination or not departure_date:
                return JsonResponse({"error": "Missing required input fields!"}, status=400)

            if any(len(value) > 50 for value in [origin, destination, departure_date]):
                return JsonResponse({"error": "Input values are too long!"}, status=400)

            if any(char in origin + destination for char in "<>""'{}[]()|&;"):
                return JsonResponse({"error": "Invalid characters in input!"}, status=400)

            # Call flight search service
            result = search_flight_service(origin, destination, departure_date)
            return JsonResponse(result, safe=False, status=200 if "error" not in result else 500)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format!"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Method not allowed!"}, status=405)


@csrf_exempt
@require_POST
def rcm_hotel(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        search_term = data.get("province", "").strip()

        if not search_term:
            return JsonResponse({"error": "Please provide a province or a nearby place.", "status": 400}, status=400)

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