import json
import os
from datetime import datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from .flight import search_flight_service
from .hotel import generate_hotel_search_url, fetch_and_process_json
from .processed import processed_data, recommend_trip, search_by_location, search_by_key, search_by_location_and_key
from django.middleware.csrf import get_token
from django.db import connection

@method_decorator(csrf_exempt, name="dispatch")
class RCMTravelDay(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        location = request.data.get("location", "").strip()
        if not location:
            return Response({"error": "Thiếu location"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            food, places = processed_data(*args, **kwargs)
            recommendations = recommend_trip(location, food, places, *args, **kwargs)
            return Response({
                "recommendations": recommendations,
                "location": location,
                "timestamp": datetime.now().isoformat(),
                "csrf_token": get_token(request)
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name="dispatch")
class RCMLocationAndKeywords(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        location = request.data.get("location", "").strip()
        keywords = request.data.get("keywords", "").strip()
        if not location or not keywords:
            return Response({"error": "Thiếu location hoặc keywords"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            results = {
                "locationResults": search_by_location(location, *args, **kwargs),
                "keywordResults": search_by_key(keywords, *args, **kwargs),
                "combinedResults": search_by_location_and_key(keywords, location, *args, **kwargs),
                "timestamp": datetime.now().isoformat(),
                "csrf_token": get_token(request)
            }
            return Response(results, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name="dispatch")
class RCMFlight(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            result = search_flight_service(
                data.get("origin", "").strip().lower(),
                data.get("destination", "").strip().lower(),
                data.get("departure_date", "").strip(),
                data.get("return_date", "").strip() or None
            )
            return Response({"result": result, "csrf_token": get_token(request)}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name="dispatch")
class RCMHotel(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            location, check_in, check_out, adults = map(lambda x: data.get(x, "").strip(), ["location", "check_in", "check_out", "adults"])
            if not all([location, check_in, check_out, adults]):
                return Response({"error": "Thiếu thông tin đầu vào"}, status=status.HTTP_400_BAD_REQUEST)
            search_url = generate_hotel_search_url(location, check_in, check_out, adults, os.getenv("HOTEL_KEY"))
            return Response({"data": fetch_and_process_json(search_url), "csrf_token": get_token(request)}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

