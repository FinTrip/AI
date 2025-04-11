import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_weather(city, forecast_days=0, monthly_avg=False):
    api_key = os.getenv("WEATHER_API_KEY")
    base_url = os.getenv("WEATHER_BASE_URL")

    # Kiểm tra biến môi trường có được thiết lập hay không
    if not api_key or not base_url:
        return {"error": "Thiếu biến môi trường WEATHER_API_KEY hoặc WEATHER_BASE_URL."}

    params = {
        "key": api_key,
        "q": f"{city},Vietnam",
        "format": "json",
        "lang": "vi"
    }

    if forecast_days > 0:
        params["num_of_days"] = forecast_days
        params["tp"] = 24
    elif monthly_avg:
        params.update({"fx": "no", "cc": "no", "mca": "yes"})

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Lỗi khi gọi API: {str(e)}"}

def display_forecast(data, start_day=0, end_day=None):
    if "error" in data:
        return {"error": data["error"]}

    try:
        forecast_list = data["data"]["weather"]
        if end_day is None or end_day > len(forecast_list):
            end_day = len(forecast_list)

        result = []
        for day in forecast_list[start_day:end_day]:
            hourly = day["hourly"][0]
            result.append({
                "Ngày": day["date"],
                "Nhiệt độ tối đa": day["maxtempC"],
                "Nhiệt độ tối tiếu": day["mintempC"],
                "Mô tả": hourly["weatherDesc"][0]["value"],
                "Độ ẩm": hourly["humidity"],
                "Tốc độ gió": hourly["windspeedKmph"],
                "Áp suất": hourly["pressure"],
                "Lượng mưa": hourly["precipMM"]
            })
        return {
            "location": data["data"]["request"][0]["query"],
            "forecast": result
        }
    except Exception as e:
        return {"error": f"Lỗi xử lý dữ liệu: {str(e)}"}
