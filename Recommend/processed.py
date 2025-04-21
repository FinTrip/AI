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

def search_province(province=None, query=None, random_mode=False):
    food_df, place_df, hotel_df = load_data(FOOD_FILE, PLACE_FILE, HOTEL_FILE)

    normalized_province = normalize_text(province) if province else None
    normalized_query = normalize_text(query) if query else None

    def filter_data(df, province_col='province', name_col='title'):
        if df is None:
            return pd.DataFrame()
        if normalized_province and normalized_query:
            return df[
                df[province_col].str.contains(normalized_province, case=False, na=False) &
                df[name_col].str.contains(normalized_query, case=False, na=False)
                ]
        elif normalized_province:
            return df[df[province_col].str.contains(normalized_province, case=False, na=False)]
        elif normalized_query:
            return df[df[name_col].str.contains(normalized_query, case=False, na=False)]
        else:
            return df

    filtered_food = filter_data(food_df, province_col='province', name_col='title')
    filtered_place = filter_data(place_df, province_col='province', name_col='title')
    filtered_hotel = filter_data(hotel_df, province_col='province', name_col='name')

    if random_mode:
        filtered_food = filtered_food.sample(frac=1) if not filtered_food.empty else filtered_food
        filtered_place = filtered_place.sample(frac=1) if not filtered_place.empty else filtered_place
        filtered_hotel = filtered_hotel.sample(frac=1) if not filtered_hotel.empty else filtered_hotel

    food_result = filtered_food.to_dict('records')
    place_result = filtered_place.to_dict('records')
    hotel_result = filtered_hotel.to_dict('records') if hotel_df is not None else []

    return {
        "province": province,
        "query": query,
        "food": food_result,
        "places": place_result,
        "hotels": hotel_result
    }

# homepage get ra random các điểm và món ăn từ 3-5 sao và không chọn lớn nhất và mỗi tỉnh 1 cái
def get_food_homepage(num_item=None):
    if num_item is None:
        num_item = random.randint(10, 15)

    try:
        df = pd.read_csv(FOOD_FILE)
        df.rename(columns={
            'Province': 'province',
            'Title': 'title',
            'Rating': 'rating',
            'Address': 'address',
            'Image': 'img'
        }, inplace=True)

        if 'description' not in df.columns:
            df['description'] = ''

        df['rating'] = pd.to_numeric(df['rating'].astype(str).str.replace(',', '.'), errors='coerce')
        df.dropna(subset=['rating', 'title'], inplace=True)
        filtered_df = df[(df['rating'] >= 3) & (df['rating'] <= 5)].drop_duplicates('title')

        if filtered_df.empty:
            return []

        unique_provinces = filtered_df['province'].unique()
        selected_foods = []

        for province in unique_provinces:
            province_df = filtered_df[filtered_df['province'] == province]
            if not province_df.empty:
                selected_foods.append(province_df.sample(1))

        if not selected_foods:
            return []

        selected_df = pd.concat(selected_foods)

        if len(selected_df) >= num_item:
            random_foods = selected_df.sample(n=num_item)
        else:
            random_foods = selected_df

        return random_foods[['title', 'rating', 'description', 'address', 'img', 'province']].fillna('N/A').to_dict(
            'records')

    except (FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        print(f"Error loading food data: {e}")
        return []


# homepage get ra random các điểm và món ăn từ 3-5 sao và không chọn lớn nhất và mỗi tỉnh 1 cái
def get_place_homepage(num_item=None):
    if num_item is None:
        num_item = random.randint(10, 15)
    df = pd.read_excel(PLACE_FILE)
    df['rating'] = pd.to_numeric(df['rating'].astype(str).str.replace(',', '.'), errors='coerce')
    df = df[(df['rating'] >= 3) & (df['rating'] <= 5)].drop_duplicates('title')

    # Lấy danh sách các tỉnh khác nhau
    unique_provinces = df['province'].unique()
    selected_places = []

    # Chọn ngẫu nhiên một địa điểm từ mỗi tỉnh
    for province in unique_provinces:
        province_df = df[df['province'] == province]
        if not province_df.empty:
            selected_places.append(province_df.sample(1))

    # Kết hợp các địa điểm đã chọn
    selected_df = pd.concat(selected_places)

    # Chọn ngẫu nhiên num_item địa điểm
    if len(selected_df) >= num_item:
        random_places = selected_df.sample(n=num_item)
    else:
        random_places = selected_df

    return random_places[['title', 'rating', 'description', 'address', 'img', 'link', 'province']].fillna(
        'N/A').to_dict('records')


#Homepage get Những Thành Phố Không Thể Bỏ Lỡ
def get_city_to_be_miss(num_cities=10):
    try:
        # Tải dữ liệu
        _, place_df, _ = load_data(FOOD_FILE, PLACE_FILE, HOTEL_FILE)

        if place_df.empty:
            return {"error": "Không có dữ liệu địa điểm."}

        # Nhóm theo tỉnh/thành phố và tính số lượng địa điểm + rating trung bình
        city_stats = place_df.groupby('province').agg({
            'rating': 'mean',
            'title': 'count'
        }).rename(columns={'title': 'place_count'})

        # Lọc các thành phố có rating trung bình >= 3.5 và số lượng địa điểm >= 5
        eligible_cities = city_stats[
            (city_stats['rating'] >= 4.0) & (city_stats['place_count'] >= 5)
        ]

        if eligible_cities.empty:
            return {"error": "Không có thành phố nào đạt tiêu chí (rating trung bình >= 3.5 và số địa điểm >= 5)."}

        # Chọn ngẫu nhiên num_cities thành phố từ danh sách đủ điều kiện
        selected_cities = eligible_cities.sample(n=min(num_cities, len(eligible_cities)), random_state=None)

        # Lấy một địa điểm ngẫu nhiên cho mỗi thành phố
        result = []
        for city in selected_cities.index:
            city_places = place_df[place_df['province'] == city]
            # Chọn ngẫu nhiên một địa điểm từ danh sách
            random_place = city_places.sample(1, random_state=None).iloc[0]

            result.append({
                "province": city,
                "place": {
                    "title": random_place['title'],
                    "rating": float(random_place['rating']) if pd.notna(random_place['rating']) else None,
                    "description": random_place.get('description', ''),
                    "address": random_place['address'],
                    "img": random_place['img'],
                    "types": random_place.get('types', []),
                    "link": random_place.get('link', '')
                },
                "average_rating": float(selected_cities.loc[city, 'rating']),
                "place_count": int(selected_cities.loc[city, 'place_count'])
            })

        return {"cities": result, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        return {"error": f"Lỗi hệ thống: {str(e)}"}
