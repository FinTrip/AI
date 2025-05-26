import pandas as pd
import re
import os
import unidecode
import random

csv_filename = os.path.join(os.path.dirname(__file__), "data", "hotelss.csv")

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
         ["name", "link", "description", "price", "name_nearby_place", "hotel_class", "img_origin", "location_rating", "animates"]}
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
             ["name", "link", "description", "price", "name_nearby_place", "hotel_class", "img_origin", "location_rating", "province", "animates"]}
            for hotel in hotels_list
        ]
        return processed_hotels
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        return []

def update_hotel_in_csv(hotel_name, update_data):
    try:
        df = pd.read_csv(csv_filename)
        if df.empty:
            return False

        normalized_hotel_name = normalize_text(hotel_name)
        mask = df['name'].apply(normalize_text) == normalized_hotel_name

        if not mask.any():
            return False

        for key, value in update_data.items():
            if value and key in df.columns:
                df.loc[mask, key] = value

        df.to_csv(csv_filename, index=False, encoding='utf-8')
        return True
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return False
    except Exception as e:
        raise Exception(f"Không thể cập nhật khách sạn: {str(e)}")

def delete_hotel_in_csv(hotel_name):
    try:
        df = pd.read_csv(csv_filename)
        if df.empty:
            return False

        normalized_hotel_name = normalize_text(hotel_name)
        mask = df['name'].apply(normalize_text) == normalized_hotel_name

        if not mask.any():
            return False

        df = df[~mask]
        df.to_csv(csv_filename, index=False, encoding='utf-8')
        return True
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return False
    except Exception as e:
        raise Exception(f"Không thể xóa khách sạn: {str(e)}")

def get_hotel_homepage(num_item=None):
    if num_item is None:
        num_item = random.randint(10, 15)

    try:
        df = pd.read_csv(csv_filename)
        if df.empty:
            return []

        df['location_rating'] = pd.to_numeric(df['location_rating'], errors='coerce')
        df.dropna(subset=['location_rating', 'name'], inplace=True)
        filtered_df = df[(df['location_rating'] >= 3) & (df['location_rating'] <= 5)].drop_duplicates('name')

        if filtered_df.empty:
            return []

        unique_provinces = filtered_df['province'].unique()
        selected_hotels = []

        for province in unique_provinces:
            province_df = filtered_df[filtered_df['province'] == province]
            if not province_df.empty:
                selected_hotels.append(province_df.sample(1))

        if not selected_hotels:
            return []

        selected_df = pd.concat(selected_hotels)

        if len(selected_df) >= num_item:
            random_hotels = selected_df.sample(n=num_item)
        else:
            random_hotels = selected_df

        return random_hotels[
            ['name', 'link', 'description', 'price', 'name_nearby_place', 'hotel_class', 'img_origin',
             'location_rating', 'province', 'animates']
        ].fillna('N/A').to_dict('records')
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        print(f"Error loading hotel data: {e}")
        return []