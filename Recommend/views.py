import json,os
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from rest_framework import status


from .flight import search_flight_service
from .hotel import process_hotel_data_from_csv
from .processed import load_data, recommend_one_day_trip, FOOD_FILE, PLACE_FILE


def validate_request(data, *required_fields):
    """Kiểm tra các trường bắt buộc trong request."""
    for field in required_fields:
        if not data.get(field, "").strip():
            return False, f"Thiếu trường bắt buộc: {field}"
    return True, None


@csrf_exempt
@require_POST
def recommend_travel_day(request):
    """API gợi ý món ăn + địa điểm theo tỉnh."""
    try:
        data = json.loads(request.body)
        if not data.get("location"):
            return JsonResponse({"error": "Thiếu trường bắt buộc: location"}, status=400)

        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)

        recommendations = recommend_one_day_trip(data["location"].strip(), food_df, place_df)

        return JsonResponse({
            "recommendations": recommendations,
            "location": data["location"].strip(),
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }, status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def search_location_and_keywords(request):
    """API to search for results based on location and keywords."""
    try:
        data = json.loads(request.body)
        is_valid, error_message = validate_request(data, "location", "keywords")
        if not is_valid:
            return JsonResponse({"error": error_message}, status=status.HTTP_400_BAD_REQUEST)

        # Load and process data
        food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
        results = {
            "locationResults": search_by_location(food_df, data.get("location").strip()),
            "keywordResults": search_by_key(food_df, data.get("keywords").strip()),
            "combinedResults": search_by_location_and_key(food_df, data.get("location").strip(), data.get("keywords").strip()),
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request)
        }

        return JsonResponse(results, status=status.HTTP_200_OK)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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