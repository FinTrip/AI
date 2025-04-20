import os
import ast
import pandas as pd
import unidecode
import numpy as np
import random
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.linear_model import LinearRegression

FOOD_FILE = os.path.join(os.path.dirname(__file__), "data", "food.csv")
PLACE_FILE = os.path.join(os.path.dirname(__file__), "data", "place2.xlsx")
HOTEL_FILE = os.path.join(os.path.dirname(__file__), "data", "all_hotels.csv")

def normalize_text(text):
    if isinstance(text, str):
        return unidecode.unidecode(text.lower().strip())
    return ""

def safe_literal_eval(x):
    try:
        return ast.literal_eval(x) if isinstance(x, str) else []
    except (ValueError, SyntaxError):
        return []

def verify_file_path(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

def load_data(food_path, place_path, hotel_path=None):
    verify_file_path(food_path)
    verify_file_path(place_path)
    if hotel_path:
        verify_file_path(hotel_path)

    food_df = pd.read_csv(food_path)
    place_df = pd.read_excel(place_path)
    hotel_df = pd.read_csv(hotel_path) if hotel_path else None

    food_df.rename(columns={'Province': 'province', 'Title': 'title', 'Rating': 'rating', 'Address': 'address', 'Image': 'img'}, inplace=True)
    if 'description' not in food_df.columns:
        food_df['description'] = ''
    food_df['types'] = food_df.get('Service', pd.Series([[]] * len(food_df))).apply(safe_literal_eval)

    if hotel_df is not None:
        hotel_df.rename(columns={'province': 'province', 'name': 'name', 'link': 'link', 'description': 'description', 'price': 'price', 'name_nearby_place': 'name_nearby_place', 'hotel_class': 'hotel_class', 'img_origin': 'img_origin', 'location_rating': 'location_rating', 'animates': 'animates'}, inplace=True)

    for df in [df for df in [food_df, place_df, hotel_df] if df is not None]:
        if 'rating' in df.columns:
            df['rating'] = pd.to_numeric(df['rating'].astype(str).str.replace(',', '.'), errors='coerce')
            df.dropna(subset=['rating'], inplace=True)
        elif 'location_rating' in df.columns:
            df['location_rating'] = pd.to_numeric(df['location_rating'].astype(str).str.replace(',', '.'), errors='coerce')
            df.dropna(subset=['location_rating'], inplace=True)
        if 'types' not in df.columns:
            df['types'] = [[] for _ in range(len(df))]
        else:
            df['types'] = df['types'].apply(safe_literal_eval)

    food_df['province'] = food_df['province'].apply(normalize_text)
    place_df['province'] = place_df['province'].apply(normalize_text)
    if hotel_df is not None:
        hotel_df['province'] = hotel_df['province'].apply(normalize_text)

    return food_df, place_df, hotel_df

def recommend_clustering(df, n_clusters=5):
    if df.empty:
        raise ValueError("Dataset is empty.")

    scaler = StandardScaler()
    scaled_rating = scaler.fit_transform(df[['rating']])

    indices = np.arange(len(df)).reshape(-1, 1)
    lin_reg = LinearRegression()
    lin_reg.fit(indices, scaled_rating)
    residuals = scaled_rating - lin_reg.predict(indices)
    scaled_residuals = scaler.fit_transform(residuals)

    features = np.hstack((scaled_rating, scaled_residuals))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['Cluster'] = kmeans.fit_predict(features)

    return df, {
        "silhouette_score": silhouette_score(features, df['Cluster']),
        "inertia": kmeans.inertia_
    }

def is_non_priority_place(place):
    non_priority_types = ["Trung tâm vui chơi dành cho trẻ em", "Sân chơi", "Khu trẻ em"]
    non_priority_keywords = ["thiếu nhi", "trẻ"]

    place_types = place.get('types', [])
    if any(t in place_types for t in non_priority_types):
        return True

    title = normalize_text(place.get('title', ''))
    if any(keyword in title for keyword in non_priority_keywords):
        return True

    return False

def recommend_pool(province, food_df, place_df):
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": {"priority": [], "non_priority": []}}

    food_pool = filtered_food.drop_duplicates('title').sort_values(by='rating', ascending=False)[
        ['title', 'rating', 'description', 'address', 'img']
    ].to_dict('records')

    place_pool = filtered_place.drop_duplicates('title').sort_values(by='rating', ascending=False)[
        ['title', 'rating', 'description', 'address', 'img', 'link', 'types']
    ].to_dict('records')

    priority_pool = [place for place in place_pool if not is_non_priority_place(place)]
    non_priority_pool = [place for place in place_pool if is_non_priority_place(place)]

    return {
        "food": food_pool,
        "places": {
            "priority": priority_pool,
            "non_priority": non_priority_pool
        }
    }

def recommend_schedule(start_day, end_day, province, food_df, place_df, random_mode=False):
    fmt = "%Y-%m-%d"
    try:
        start = datetime.strptime(start_day, fmt)
        end = datetime.strptime(end_day, fmt)
    except ValueError:
        return {"error": "Invalid date format. Please use YYYY-MM-DD."}

    total_days = (end - start).days + 1
    if total_days < 1:
        return {"error": "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu."}

    pool = recommend_pool(province, food_df, place_df)
    pool_food = pool["food"].copy()
    priority_places = pool["places"]["priority"].copy()
    non_priority_places = pool["places"]["non_priority"].copy()

    if random_mode:
        random.shuffle(pool_food)
        random.shuffle(priority_places)
        random.shuffle(non_priority_places)

    def group_by_district(places):
        district_to_places = {}
        for place in places:
            parts = place.get("address", "").split(", ")
            district = parts[-3] if len(parts) >= 3 else "unknown"
            district_to_places.setdefault(district, []).append(place)
        for district in district_to_places:
            if random_mode:
                random.shuffle(district_to_places[district])
        return district_to_places

    priority_districts = group_by_district(priority_places)
    non_priority_districts = group_by_district(non_priority_places)

    def select_place(used_districts):
        available = [d for d in priority_districts if priority_districts[d] and d not in used_districts]
        if available:
            district = random.choice(available)
            return priority_districts[district].pop(0)

        available = [d for d in non_priority_districts if non_priority_districts[d] and d not in used_districts]
        if available:
            district = random.choice(available)
            return non_priority_districts[district].pop(0)

        available = [d for d in priority_districts if priority_districts[d]]
        if available:
            district = random.choice(available)
            return priority_districts[district].pop(0)

        available = [d for d in non_priority_districts if non_priority_districts[d]]
        if available:
            district = random.choice(available)
            return non_priority_districts[district].pop(0)

        return {}

    def select_food():
        if pool_food:
            return pool_food.pop(0)
        return {}

    if total_days <= 5:
        num_food_per_day = 2
        num_place_per_day = 2
    elif total_days <= 10:
        num_food_per_day = 2
        num_place_per_day = 2
    else:
        num_food_per_day = 1
        num_place_per_day = 1

    schedule = []
    for i in range(total_days):
        day = start + pd.Timedelta(days=i)
        used_districts = set()
        itinerary = []

        for _ in range(num_food_per_day):
            food = select_food()
            if food:
                itinerary.append({"type": "food", "details": food})

        for _ in range(num_place_per_day):
            place = select_place(used_districts)
            if place:
                itinerary.append({"type": "place", "details": place})

        schedule.append({"day": f"Day {i + 1} ({day.strftime(fmt)})", "itinerary": itinerary})

    return {
        "total_days": total_days,
        "start_day": start_day,
        "end_day": end_day,
        "province": province,
        "schedule": schedule
    }