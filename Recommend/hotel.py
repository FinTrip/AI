import os
import re
import requests
from django.http import JsonResponse
from dotenv import load_dotenv
from rest_framework.utils import json

load_dotenv()

def generate_hotel_search_url(location, check_in, check_out, adults, api_key):
    params = {
        "engine": "google_hotels",
        "q": location.replace(" ", "+"),
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": adults,
        "currency": "VND",
        "gl": "vn",
        "hl": "vi",
        "api_key": api_key
    }
    query_string = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{os.getenv('HOTEL_URL')}?{query_string}"

def fetch_and_process_json(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        properties = data.get("properties", [])

        if not properties:
            return JsonResponse({"error": "Không tìm thấy dữ liệu 'properties'."}, status=404)

        hotels_list = []

        for hotel in properties:
            name = hotel.get("name", "Không có tên")
            description = hotel.get("description", "Không có mô tả")
            link = hotel.get("link", "Không có link")

            pricePerNight = 0
            rate_per_night = hotel.get("rate_per_night", {})
            lowest = rate_per_night.get("lowest")

            checknight = False
            if lowest:
                lowest_cleaned = re.sub(r"[^0-9]", "", lowest)
                if lowest_cleaned:
                    pricePerNight = int(lowest_cleaned) * 245000
                    checknight = True

            pricerate = 0
            total_rate = hotel.get("total_rate", {})
            lower = total_rate.get("lowest")
            if lower:
                lower_cleaned = re.sub(r"[^0-9]", "", lower)
                if lower_cleaned:
                    pricerate = int(lower_cleaned) * 245000

            price = str(pricePerNight if checknight else pricerate)

            name_nearby_place = [near.get("name", "Không có tên") for near in hotel.get("nearby_places", [])]
            img_origin = [img.get("original_image", "Không có ảnh") for img in hotel.get("images", [])]

            hotel_class = hotel.get("hotel_class", "Không có hạng sao")
            location_rating = hotel.get("location_rating", "Không có đánh giá vị trí")
            amenities = hotel.get("amenities", [])

            hotels_list.append({
                "name": name,
                "link": link,
                "description": description,
                "price": price,
                "name_nearby_place": name_nearby_place,
                "hotel_class": hotel_class,
                "img_origin": img_origin,
                "location_rating": location_rating,
                "amenities": amenities
            })

        return JsonResponse({"hotels": hotels_list}, json_dumps_params={"ensure_ascii": False}, safe=False)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": f"Lỗi khi lấy dữ liệu: {str(e)}"}, status=500)
