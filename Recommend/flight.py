import os
import requests
from django.http import JsonResponse
from dotenv import load_dotenv

airport_info = {
    "quảng nam": "VCL", "chu lai": "VCL", "thanh hóa": "THD", "thọ xuân": "THD",
    "quảng bình": "VDH", "đồng hới": "VDH", "điện biên": "DIN", "điện biên phủ": "DIN",
    "phú yên": "TBB", "tuy hòa": "TBB", "gia lai": "PXU", "pleiku": "PXU",
    "đắk lắk": "BMV", "buôn mê thuột": "BMV", "kiên giang": "VKG", "rạch giá": "VKG",
    "cà mau": "CAH", "vũng tàu": "VCS", "bà rịa – vũng tàu": "VCS", "côn đảo": "VCS", "hà nội": "HAN",
    "nội bài": "HAN", "hồ chí minh": "SGN", "tân sơn nhất": "SGN", "sài gòn": "SGN",
    "kiên giang": "PQC", "phú quốc": "PQC", "đà nẵng": "DAD", "khánh hòa": "CXR",
    "cam ranh": "CXR", "huế": "HUI", "thừa thiên huế": "HUI", "phú bài": "HUI", "quảng ninh": "VDO",
    "vân đồn": "VDO", "cần thơ": "VCA", "nghệ an": "VII", "vinh": "VII", "bình định": "UIH",
    "phù cát": "UIH", "hải phòng": "HPH", "cát bi": "HPH", "lâm đồng": "DLI", "liên khương": "DLI"
}

load_dotenv()

def get_access_token():
    data = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("AMADEUS_CLIENT_ID"),
        "client_secret": os.getenv("AMADEUS_CLIENT_SECRET")
    }
    response = requests.post(os.getenv("AMADEUS_API_URL"), data=data)
    return response.json().get("access_token")

#xử lý dữ liệu data
def process_flight_data(data,round_trip):
    flight_results = []
    if "data" in data:
        for flight in data["data"]:
            itineraries = flight["itineraries"]
            price = flight["price"]
            total_price_vnd= float(price["total"]) * 27500
            base_price_vnd = float(price["base"]) * 27500

            fare_basis = flight["travelerPricings"][0]["fareDetailsBySegment"][0]["fareBasis"]
            cabin = flight["travelerPricings"][0]["fareDetailsBySegment"][0]["cabin"]

            outbound = itineraries[0]["segments"][0]
            outbound_time = outbound["departure"]["at"]
            outbound_flight_code = f"{outbound['carrierCode']}{outbound['number']}"

            flight_data = {
                "outbound_flight_code" : outbound_flight_code,
                "outbound_time" : outbound_time,
                "total_price_vnd" : f"{total_price_vnd} VNĐ",
                "base_price_vnd" : f"{base_price_vnd} VNĐ",
                "fare_basis" : fare_basis,
                "cabin" : cabin
            }

            if round_trip:
                inbound = itineraries[1]["segments"][0]
                inbound_time = inbound["departure"]["at"]
                inbound_flight_code = f"{inbound['carrierCode']}{inbound['number']}"
                flight_data.update({
                    "inbound_flight_code": inbound_flight_code,
                    "inbound_time": inbound_time
                })

            flight_results.append(flight_data)

    return flight_results if flight_results else  JsonResponse({"error": "Không tìm được chuyến bay phù hơp!"}, status=404)

def search_flight_service(origin_city, destination_city, departure_date, return_date=None):
    token = get_access_token()
    if not token:
        return JsonResponse({"error":"Không thể lấy Access Token"}, status=404)

    origin = airport_info.get(origin_city.lower())
    destination = airport_info.get(destination_city.lower())

    if not origin or not destination:
        return JsonResponse({"error":"Thành phố hoặc tên sân bay không đúng"}, status=404)

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"

    header = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": 1,
        "max": 5
    }

    if return_date:
        params["returnDate"] = return_date

    response = requests.get(url, headers=header, params=params)
    return process_flight_data(response.json(), bool(return_date))