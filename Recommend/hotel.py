import pandas as pd
import re
import os
import unidecode  # Dùng để bỏ dấu tiếng Việt
import random

from pyexpat import error

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

def show_hotel_in_csv():
    try:
        df = pd.read_csv(csv_filename)
        if df.empty:
            return []
        hotels_list = df.to_dict(orient="records")
        processed_hotels = [
            {key: str(hotel.get(key, f"No {key}")) for key in
             ["name", "link", "description", "price", "name_nearby_place", "hotel_class", "img_origin", "location_rating", "province"]}
            for hotel in hotels_list
        ]
        return processed_hotels
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        return []

def update_hotel_in_csv(hotel_name, update_data):
    try:
        # Đọc file CSV
        df = pd.read_csv(csv_filename)
        if df.empty:
            return False

        # Tìm khách sạn dựa trên tên (so sánh không phân biệt hoa thường, bỏ dấu)
        normalized_hotel_name = normalize_text(hotel_name)
        mask = df['name'].apply(normalize_text) == normalized_hotel_name

        if not mask.any():
            return False  # Không tìm thấy khách sạn

        # Cập nhật các trường được cung cấp
        for key, value in update_data.items():
            if value and key in df.columns:  # Chỉ cập nhật nếu giá trị không rỗng và cột tồn tại
                df.loc[mask, key] = value

        # Lưu lại file CSV
        df.to_csv(csv_filename, index=False, encoding='utf-8')
        return True

    except (FileNotFoundError, pd.errors.EmptyDataError):
        return False
    except Exception as e:
        raise Exception(f"Không thể cập nhật khách sạn: {str(e)}")

def delete_hotel_in_csv(hotel_name):
    try:
        # Đọc file CSV
        df = pd.read_csv(csv_filename)
        if df.empty:
            return False

        # Tìm khách sạn dựa trên tên (so sánh không phân biệt hoa thường, bỏ dấu)
        normalized_hotel_name = normalize_text(hotel_name)
        mask = df['name'].apply(normalize_text) == normalized_hotel_name

        if not mask.any():
            return False  # Không tìm thấy khách sạn

        # Xóa bản ghi
        df = df[~mask]

        # Lưu lại file CSV
        df.to_csv(csv_filename, index=False, encoding='utf-8')
        return True

    except (FileNotFoundError, pd.errors.EmptyDataError):
        return False
    except Exception as e:
        raise Exception(f"Không thể xóa khách sạn: {str(e)}")

def get_hotel_homepage(num_item = None):
    if num_item is None:
        num_item = random.randint(10,15)

    try:
        df = pd.read_csv(csv_filename)
        if df.empty:
            return []
        df['location_rating'] = pd.to_numeric(df['location_rating'], errors= 'coerce')
        df.dropna(subset=['location_rating', 'name'],inplace=True)
        top_hotels = df.drop_duplicates('name').nlargest(num_item, 'location_rating', keep='first')
        return top_hotels[
            ['name', 'link', 'description', 'price', 'name_nearby_place', 'hotel_class', 'img_origin',
             'location_rating']
        ].fillna('N/A').to_dict('records')
    except(FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        print(f"Error loading hotel data: {e}")
        return []