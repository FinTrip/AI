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

# Đường dẫn đến file dữ liệu
FOOD_FILE = os.path.join(os.path.dirname(__file__), "data", "food.csv")
PLACE_FILE = os.path.join(os.path.dirname(__file__), "data", "place2.xlsx")

### **Hàm tiện ích**
def normalize_text(text):
    """Chuẩn hóa văn bản: chuyển về chữ thường, loại bỏ khoảng trắng thừa, bỏ dấu tiếng Việt."""
    if isinstance(text, str):
        return unidecode.unidecode(text.lower().strip())
    return ""

def safe_literal_eval(x):
    """Chuyển chuỗi thành danh sách; trả về danh sách rỗng nếu lỗi."""
    try:
        return ast.literal_eval(x) if isinstance(x, str) else []
    except (ValueError, SyntaxError):
        return []

def verify_file_path(path):
    """Kiểm tra xem file có tồn tại không; ném lỗi nếu không tìm thấy."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

### **Hàm xử lý dữ liệu**
def load_data(food_path, place_path):
    """
    Đọc và tiền xử lý dữ liệu từ file CSV (food) và Excel (place).
    - Chuẩn hóa tên cột và dữ liệu.
    - Xử lý cột rating thành dạng số.
    - Chuẩn hóa tỉnh/thành phố.
    """
    verify_file_path(food_path)
    verify_file_path(place_path)

    # Đọc dữ liệu
    food_df = pd.read_csv(food_path)
    place_df = pd.read_excel(place_path)

    # Đổi tên cột cho food_df
    food_df.rename(columns={
        'Province': 'province', 'Title': 'title', 'Rating': 'rating',
        'Address': 'address', 'Image': 'img'
    }, inplace=True)

    # Thêm cột 'description' nếu chưa có
    if 'description' not in food_df.columns:
        food_df['description'] = ''

    # Xử lý cột 'Service' thành 'types'
    food_df['types'] = food_df.get('Service', pd.Series([[]] * len(food_df))).apply(safe_literal_eval)

    # Chuẩn hóa cột rating và types
    for df in [food_df, place_df]:
        if 'rating' in df.columns:
            df['rating'] = pd.to_numeric(df['rating'].astype(str).str.replace(',', '.'), errors='coerce')
            df.dropna(subset=['rating'], inplace=True)
        if 'types' not in df.columns:
            df['types'] = [[] for _ in range(len(df))]
        else:
            df['types'] = df['types'].apply(safe_literal_eval)

    # Chuẩn hóa cột province
    food_df['province'] = food_df['province'].apply(normalize_text)
    place_df['province'] = place_df['province'].apply(normalize_text)

    return food_df, place_df

### **Hàm phân cụm**
def perform_clustering(df, n_clusters=5):
    """
    Phân cụm dữ liệu dựa trên rating và residual từ hồi quy tuyến tính.
    - Sử dụng LinearRegression để tạo đặc trưng residual.
    - Trả về DataFrame với cột 'Cluster' và thông tin đánh giá phân cụm.
    """
    if df.empty:
        raise ValueError("Dataset is empty.")

    # Chuẩn hóa rating
    scaler = StandardScaler()
    scaled_rating = scaler.fit_transform(df[['rating']])

    # Tạo đặc trưng residual từ hồi quy tuyến tính
    indices = np.arange(len(df)).reshape(-1, 1)
    lin_reg = LinearRegression()
    lin_reg.fit(indices, scaled_rating)
    residuals = scaled_rating - lin_reg.predict(indices)
    scaled_residuals = scaler.fit_transform(residuals)

    # Kết hợp đặc trưng
    features = np.hstack((scaled_rating, scaled_residuals))

    # Phân cụm bằng KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['Cluster'] = kmeans.fit_predict(features)

    return df, {
        "silhouette_score": silhouette_score(features, df['Cluster']),
        "inertia": kmeans.inertia_
    }

### **Hàm gợi ý**
def recommend_one_day_trip(province, food_df, place_df, max_items=3, random_mode=False):
    """
    Gợi ý lịch trình 1 ngày: max_items món ăn và max_items địa điểm.
    - Nếu random_mode=True: Chọn ngẫu nhiên từ danh sách.
    - Nếu random_mode=False: Chọn theo rating cao nhất.
    """
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    # Xử lý food
    filtered_food = filtered_food.drop_duplicates('title')
    if random_mode:
        food_result = filtered_food.sample(n=min(max_items, len(filtered_food)))[
            ['title', 'rating', 'description', 'address', 'img']
        ].to_dict('records')
    else:
        food_result = filtered_food.nlargest(max_items, 'rating')[
            ['title', 'rating', 'description', 'address', 'img']
        ].to_dict('records')

    # Xử lý place
    filtered_place = filtered_place.drop_duplicates('title')
    if random_mode:
        place_result = filtered_place.sample(n=min(max_items, len(filtered_place)))[
            ['title', 'rating', 'description', 'address', 'img', 'link']
        ].to_dict('records')
    else:
        place_result = filtered_place.nlargest(max_items, 'rating')[
            ['title', 'rating', 'description', 'address', 'img', 'link']
        ].to_dict('records')

    return {"food": food_result, "places": place_result}

def get_recommendation_pool(province, food_df, place_df):
    """
    Tạo pool gợi ý đầy đủ cho một tỉnh/thành phố, sắp xếp theo rating giảm dần.
    """
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    food_pool = filtered_food.drop_duplicates('title').sort_values(by='rating', ascending=False)[
        ['title', 'rating', 'description', 'address', 'img']
    ].to_dict('records')

    place_pool = filtered_place.drop_duplicates('title').sort_values(by='rating', ascending=False)[
        ['title', 'rating', 'description', 'address', 'img', 'link']
    ].to_dict('records')

    return {"food": food_pool, "places": place_pool}

def recommend_trip_schedule(start_day, end_day, province, food_df, place_df, random_mode=False):
    """
    Tạo lịch trình nhiều ngày từ start_day đến end_day cho một tỉnh/thành phố.
    - Mỗi ngày gồm: sáng (1 ăn + 1 đi), trưa (1 ăn), chiều (1 đi), tối (1 ăn + 1 đi).
    - Địa điểm ưu tiên chọn từ các quận khác nhau trong ngày.
    - Nếu random_mode=True: Chọn ngẫu nhiên từ pool.
    """
    fmt = "%Y-%m-%d"
    try:
        start = datetime.strptime(start_day, fmt)
        end = datetime.strptime(end_day, fmt)
    except ValueError:
        return {"error": "Invalid date format. Please use YYYY-MM-DD."}

    total_days = (end - start).days + 1
    if total_days < 1:
        return {"error": "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu."}

    # Lấy pool gợi ý
    pool = get_recommendation_pool(province, food_df, place_df)
    pool_food = pool["food"].copy()
    pool_place = pool["places"].copy()

    if random_mode:
        random.shuffle(pool_food)
        random.shuffle(pool_place)

    # Nhóm địa điểm theo quận
    district_to_places = {}
    for place in pool_place:
        parts = place.get("address", "").split(", ")
        district = parts[-3] if len(parts) >= 3 else "unknown"
        district_to_places.setdefault(district, []).append(place)
    for district in district_to_places:
        if random_mode:
            random.shuffle(district_to_places[district])

    # Hàm chọn địa điểm
    def select_place(used_districts):
        available = [d for d in district_to_places if district_to_places[d] and d not in used_districts]
        if available:
            district = random.choice(available)
        else:
            available = [d for d in district_to_places if district_to_places[d]]
            district = random.choice(available) if available else None
        return district_to_places[district].pop(0) if district else {}

    # Hàm chọn món ăn
    def select_food():
        if pool_food:
            return pool_food.pop(0)
        return {}

    # Tạo lịch trình
    schedule = []
    for i in range(total_days):
        day = start + pd.Timedelta(days=i)
        used_districts = set()
        itinerary = [
            {"timeslot": "morning", "food": select_food(), "place": select_place(used_districts)},
            {"timeslot": "noon", "food": select_food()},
            {"timeslot": "afternoon", "place": select_place(used_districts)},
            {"timeslot": "evening", "food": select_food(), "place": select_place(used_districts)}
        ]
        schedule.append({"day": f"Day {i+1} ({day.strftime(fmt)})", "itinerary": itinerary})

    return {
        "total_days": total_days,
        "start_day": start_day,
        "end_day": end_day,
        "province": province,
        "schedule": schedule
    }

### **Hàm tìm kiếm**
def search_place(province, random_mode=False):
    """Tìm kiếm tất cả món ăn và địa điểm theo tỉnh/thành phố, có thể chọn ngẫu nhiên."""
    food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if random_mode:
        food_result = filtered_food.sample(frac=1).to_dict('records')
        place_result = filtered_place.sample(frac=1).to_dict('records')
    else:
        food_result = filtered_food.to_dict('records')
        place_result = filtered_place.to_dict('records')

    return {
        "province": province,
        "food": food_result,
        "places": place_result
    }

# homepage get ra những món ăn có do rating cao nhất
def get_food_homepage(num_item=None):
    if num_item is None:
        num_item = random.randint(10, 15)

    try:
        df = pd.read_csv(FOOD_FILE)
        df.rename(columns={
            'Province': 'province', 'Title': 'title', 'Rating': 'rating',
            'Address': 'address', 'Image': 'img'
        },inplace=True)
        if 'description' not in df.columns:
            df['description'] = ''
        if df.empty:
            return []
        df['rating'] = pd.to_numeric(df['rating'].astype(str).str.replace(',','.'), errors='coerce')
        df.dropna(subset=['rating', 'title'], inplace=True)
        top_foods = df.drop_duplicates('title').nlargest(num_item, 'rating', keep='first')
        return top_foods[
            ['title', 'rating', 'description', 'address', 'img']
        ].fillna('N/A').to_dict('records')
    except(FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        print(f"Error loading food data: {e}")
        return []

# homepage get ra những món ăn có do rating cao nhất
def get_place_homepage(num_item=None):
    if num_item is None:
        num_item = random.randint(10, 15)

    try:
        df = pd.read_excel(PLACE_FILE)
        df['rating'] = pd.to_numeric(df['rating'].astype(str).str.replace(',','.'), errors='coerce')
        df.dropna(subset=['rating', 'title'], inplace=True)
        non_hotel_df = df[
            ~df.get('types', pd.Series([''] * len(df))).apply(lambda x: 'hotel' in normalize_text(x)) &
            ~df['title'].apply(normalize_text).str.contains('hotel', na=False)
            ].drop_duplicates('title')
        top_place = non_hotel_df.drop_duplicates('title').nlargest(num_item, 'rating', keep='first')
        return top_place[
            ['title', 'rating', 'description', 'address', 'img', 'link']
        ].fillna('N/A').to_dict('records')
    except(FileNotFoundError, pd.errors.EmptyDataError):
        return []
    except Exception as e:
        print(f"Error loading place data: {e}")
        return []