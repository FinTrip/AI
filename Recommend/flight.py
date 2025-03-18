import os
import requests
from django.http import JsonResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Airport code mapping
airport_info = {
    "quảng nam": "VCL", "chu lai": "VCL", "thanh hóa": "THD", "thọ xuân": "THD",
    "quảng bình": "VDH", "đồng hới": "VDH", "điện biên": "DIN", "điện biên phủ": "DIN",
    "phú yên": "TBB", "tuy hòa": "TBB", "gia lai": "PXU", "pleiku": "PXU",
    "đắk lắk": "BMV", "buôn mê thuột": "BMV", "kiên giang": "VKG", "rạch giá": "VKG",
    "cà mau": "CAH", "vũng tàu": "VCS", "bà rịa – vũng tàu": "VCS", "côn đảo": "VCS", "hà nội": "HAN",
    "nội bài": "HAN", "hồ chí minh": "SGN", "tân sơn nhất": "SGN", "sài gòn": "SGN",
    "phú quốc": "PQC", "đà nẵng": "DAD", "khánh hòa": "CXR", "cam ranh": "CXR",
    "huế": "HUI", "thừa thiên huế": "HUI", "phú bài": "HUI", "quảng ninh": "VDO",
    "vân đồn": "VDO", "cần thơ": "VCA", "nghệ an": "VII", "vinh": "VII", "bình định": "UIH",
    "phù cát": "UIH", "hải phòng": "HPH", "cát bi": "HPH", "lâm đồng": "DLI", "liên khương": "DLI"
}

def get_access_token():
    """Retrieve access token from Amadeus API."""
    data = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("AMADEUS_CLIENT_ID"),
        "client_secret": os.getenv("AMADEUS_CLIENT_SECRET")
    }
    response = requests.post(os.getenv("AMADEUS_API_URL"), data=data)

    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def process_flight_data(data):
    """Process flight data returned by Amadeus API."""
    flight_results = []
    if "data" in data:
        for flight in data["data"]:
            try:
                itineraries = flight["itineraries"]
                price = flight["price"]
                total_price_vnd = float(price["total"]) * 27500
                base_price_vnd = float(price["base"]) * 27500

                outbound = itineraries[0]["segments"][0]
                outbound_time = outbound["departure"]["at"]
                outbound_flight_code = f"{outbound['carrierCode']}{outbound['number']}"

                # Lấy thông tin loại vé & khoang nếu có, mặc định ESP & ECONOMY
                traveler_pricing = flight.get("travelerPricings", [{}])
                fare_basis = traveler_pricing[0].get("fareDetailsBySegment", [{}])[0].get("fareBasis", "ESP")
                cabin = traveler_pricing[0].get("fareDetailsBySegment", [{}])[0].get("cabin", "ECONOMY")

                flight_data = {
                    "outbound_flight_code": outbound_flight_code,
                    "outbound_time": outbound_time,
                    "total_price_vnd": f"{total_price_vnd:,.0f} VNĐ",
                    "base_price_vnd": f"{base_price_vnd:,.0f} VNĐ",
                    "fare_basis": fare_basis,
                    "cabin": cabin
                }

                flight_results.append(flight_data)
            except (KeyError, IndexError) as e:
                print(f"Error processing flight data: {e}")

    return flight_results

def search_flight_service(origin_city, destination_city, departure_date):
    """Search for flights using Amadeus API."""
    token = get_access_token()
    if not token:
        return {"error": "Không thể lấy Access Token"}

    origin = airport_info.get(origin_city.lower())
    destination = airport_info.get(destination_city.lower())

    if not origin or not destination:
        return {"error": "Thành phố hoặc tên sân bay không đúng"}

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    header = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": 1,
        "max": 5
    }

    response = requests.get(url, headers=header, params=params)
    if response.status_code == 200:
        return process_flight_data(response.json())
    return {"error": "Lỗi kết nối đến API Amadeus"}
