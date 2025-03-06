import requests
import httpx
import asyncio

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .processed import processed_data, recommend_trip, search_by_location, search_by_key, search_by_location_and_key

SPRING_BOOT_URL1 = 'http://localhost:8080/indentity/receive-data-travel'
SPRING_BOOT_URL2 = 'http://localhost:8080/indentity/receive-data-locationkey'


@method_decorator(csrf_exempt, name='dispatch')
class RCMTravelDay(APIView):
    permission_classes = [AllowAny]

    def get(self,request,format=None):
        location = request.GET.get('location', '').strip()
        if not location:
            return Response({"error": "Missing location parameter"}, status=status.HTTP_400_BAD_REQUEST)
        request.session['global_location']= location
        return Response({"message": f"Location '{location}' received successfully"}, status=status.HTTP_200_OK)

    async def post(self, request, format=None):
        location = request.session.get('global_location')


        if not location:
            return Response({"error": "No location received from GET request"}, status=status.HTTP_400_BAD_REQUEST)

        processed_food, processed_place = processed_data()

        food_recommendations, place_recommendations = recommend_trip(location, processed_food, processed_place)

        food_list = list(food_recommendations)
        place_list = list(place_recommendations)

        context = {"food_list" : food_list, "place_list" :place_list}

        async with httpx.AsyncClient() as client:
            try:
                # Gửi request POST đến API của Java Spring
                response = await client.post(SPRING_BOOT_URL1, json=context, timeout=5)
                if response.status_code == 200:
                    return Response({
                        "message": "Data sent to Java Spring successfully",
                        "spring_response": response.json()
                    }, status=status.HTTP_200_OK)
                return Response({"error": "Spring Boot returned an error"}, status=response.status_code)

            except httpx.RequestError as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class RCMLocationAndKeywords(APIView):
    permission_classes = [AllowAny]

    def get(self, request, format=None):
        location = request.GET.get("location", '').strip()
        keywords = request.GET.get("keywords", '').strip()

        if not location or not keywords:
            return Response({"error": "Missing location or keywords parameter"}, status=status.HTTP_400_BAD_REQUEST)

        request.session['travel_location'] = location
        request.session['travel_keywords'] = keywords

        return Response({"message": f"Location '{location}' & Keywords '{keywords}' received successfully"}, status=status.HTTP_200_OK)

    async def post(self, request, format=None):
        location = request.session.get('travel_location')
        keywords = request.session.get('travel_keywords')

        if not location or not keywords:
            return Response({"error": "No location or keywords received from GET request"},
                            status=status.HTTP_400_BAD_REQUEST)

        location = search_by_location(location)
        key = search_by_key(keywords)
        results = search_by_location_and_key(keywords, location)

        context = {"location" : location, "key" : key, "results" : results}

        async with httpx.AsyncClient() as client:
            try:
                # Gửi request POST đến API của Java Spring
                response = await client.post(SPRING_BOOT_URL2, json=context, timeout=5)
                if response.status_code == 200:
                    return Response({
                        "message": "Data sent to Java Spring successfully",
                        "spring_response": response.json()
                    }, status=status.HTTP_200_OK)
                return Response({"error": "Spring Boot returned an error"}, status=response.status_code)

            except httpx.RequestError as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
