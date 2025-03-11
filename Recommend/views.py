import asyncio
import json
from datetime import datetime

from django.contrib.admin.templatetags.admin_list import results
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .flight import search_flight_service
from .processed import processed_data, recommend_trip, search_by_location, search_by_key, search_by_location_and_key


@method_decorator(csrf_exempt, name="dispatch")
class RCMTravelDay(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        location = request.GET.get("location", "").strip()
        if not location:
            return Response({"error": "Thiếu tham số location"}, status=status.HTTP_400_BAD_REQUEST)

        request.session["global_location"] = location
        return Response({"message": f"Location '{location}' received successfully"}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        location = request.data.get("location")

        if not location:
            return Response({"error": "Không có location"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            processed_food, processed_place = processed_data(*args, **kwargs)
            food_recommendations, place_recommendations = recommend_trip(location, processed_food, processed_place, *args, **kwargs)

            return Response(
                {
                    "recommendations": {
                        "food": food_recommendations,
                        "places": place_recommendations,
                    },
                    "location": location,
                    "timestamp": datetime.now().isoformat(),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name="dispatch")
class RCMLocationAndKeywords(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        location = request.GET.get("location", "").strip()
        keywords = request.GET.get("keywords", "").strip()

        if not location or not keywords:
            return Response({"error": "Thiếu tham số location hoặc keywords"}, status=status.HTTP_400_BAD_REQUEST)

        request.session["travel_location"] = location
        request.session["travel_keywords"] = keywords

        return Response({"message": f"Location '{location}' & Keywords '{keywords}' received successfully"}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        location = request.data.get("location")
        keywords = request.data.get("keywords")

        if not location or not keywords:
            return Response({"error": "Không có location hoặc keywords"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            location_results = search_by_location(location, *args, **kwargs)
            key_results = search_by_key(keywords, *args, **kwargs)
            combined_results = search_by_location_and_key(keywords, location, *args, **kwargs)

            return Response(
                {
                    "locationResults": location_results,
                    "keywordResults": key_results,
                    "combinedResults": combined_results,
                    "timestamp": datetime.now().isoformat(),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name="dispatch")
class RCMFlight(APIView):

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            result = search_flight_service(
                data.get("origin", "").strip().lower(),
                data.get("destination", "").strip().lower(),
                data.get("departure_date", "").strip(),
                data.get("return_date","").strip() or None
            )
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error" : str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)