import pandas as pd
import re
import os
import unidecode  # Dùng để bỏ dấu tiếng Việt

csv_filename = os.path.join(os.path.dirname(__file__), "data", "hotels.csv")


def sanitize_input(input_str):
    """Loại bỏ ký tự đặc biệt"""
    return re.sub(r"[^\w\s]", "", input_str.strip())


def normalize_text(text):
    """Chuyển đổi chữ có dấu thành không dấu và viết thường"""
    return unidecode.unidecode(text).lower().strip() if text else ""


def process_hotel_data_from_csv(search_term):
    """Xử lý dữ liệu khách sạn từ file CSV dựa trên tỉnh hoặc địa danh gần đó"""
    try:
        df = pd.read_csv(csv_filename)
        if df.empty:
            return []
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception:
        return []

    search_term = normalize_text(search_term)
    hotels_list = df.to_dict(orient="records")

    processed_hotels = [
        {key: str(hotel.get(key, f"No {key}")) for key in
         ["name", "link", "description", "price", "name_nearby_place", "hotel_class", "img_origin", "location_rating"]}
        for hotel in hotels_list
        if search_term in normalize_text(str(hotel.get("province", ""))) or search_term in normalize_text(
            str(hotel.get("name_nearby_place", "")))
    ]

    return processed_hotels