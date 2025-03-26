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

# Đường dẫn đến file CSV (đảm bảo file CSV nằm trong thư mục "data" cùng với file processed.py)
FOOD_FILE = os.path.join(os.path.dirname(__file__), "data", "food.csv")
PLACE_FILE = os.path.join(os.path.dirname(__file__), "data", "place.csv")


def normalize_text(text):
    """
    Chuẩn hóa văn bản: chuyển về chữ thường, loại bỏ khoảng trắng, bỏ dấu tiếng Việt.
    """
    if isinstance(text, str):
        return unidecode.unidecode(text.lower().strip())
    return ""


def safe_literal_eval(x):
    """
    Chuyển đổi chuỗi thành danh sách; nếu lỗi thì trả về danh sách rỗng.
    """
    try:
        return ast.literal_eval(x) if isinstance(x, str) else []
    except (ValueError, SyntaxError):
        return []


def verify_file_path(path):
    """
    Kiểm tra file có tồn tại không.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")


def load_data(food_path, place_path):
    """
    Đọc và xử lý dữ liệu từ CSV.
    - Đổi tên cột của food.csv cho đồng nhất.
    - Xử lý cột rating (chuyển thành số).
    - Chuẩn hóa cột province.
    """
    verify_file_path(food_path)
    verify_file_path(place_path)

    food_df = pd.read_csv(food_path)
    place_df = pd.read_csv(place_path)

    # Đổi tên cột cho food_df
    rename_food_columns = {
        'Province': 'province',
        'Title': 'title',
        'Rating': 'rating',
        'Address': 'address',
        'Image': 'img'
    }
    food_df.rename(columns=rename_food_columns, inplace=True)

    # Thêm cột 'description' nếu chưa có
    if 'description' not in food_df.columns:
        food_df['description'] = ''

    # Chuyển cột 'Service' thành 'types'
    if 'Service' in food_df.columns:
        food_df['types'] = food_df['Service'].apply(safe_literal_eval)
    else:
        food_df['types'] = [[] for _ in range(len(food_df))]

    # Xử lý cột 'rating' cho food_df
    if 'rating' in food_df.columns:
        food_df['rating'] = pd.to_numeric(
            food_df['rating'].astype(str).str.replace(',', '.'),
            errors='coerce'
        )
        food_df.dropna(subset=['rating'], inplace=True)

    # Xử lý cho place_df
    if 'rating' in place_df.columns:
        place_df['rating'] = pd.to_numeric(
            place_df['rating'].astype(str).str.replace(',', '.'),
            errors='coerce'
        )
        place_df.dropna(subset=['rating'], inplace=True)
    if 'types' in place_df.columns:
        place_df['types'] = place_df['types'].apply(safe_literal_eval)
    else:
        place_df['types'] = [[] for _ in range(len(place_df))]

    # Chuẩn hóa cột province
    food_df['province'] = food_df['province'].apply(normalize_text)
    place_df['province'] = place_df['province'].apply(normalize_text)

    return food_df, place_df


def perform_clustering(df, n_clusters=5):
    """
    Phân cụm dữ liệu dựa trên cột 'rating'.
    Cải tiến: Sau khi chuẩn hóa rating, dùng LinearRegression để tạo thêm một đặc trưng (residual)
    nhằm bổ sung thông tin tuyến tính, sau đó thực hiện phân cụm trên không gian 2 chiều.
    """
    if df.empty:
        raise ValueError("Dataset is empty.")

    # Chuẩn hóa rating
    features = df[['rating']]
    scaler = StandardScaler()
    scaled_rating = scaler.fit_transform(features)  # (n_samples, 1)

    # Tạo biến độc lập: chỉ số của bản ghi
    indices = np.arange(len(df)).reshape(-1, 1)

    # Huấn luyện mô hình hồi quy tuyến tính
    lin_reg = LinearRegression()
    lin_reg.fit(indices, scaled_rating)
    predicted = lin_reg.predict(indices)

    # Tính residual và chuẩn hóa
    residuals = scaled_rating - predicted
    residual_scaler = StandardScaler()
    scaled_residuals = residual_scaler.fit_transform(residuals)

    # Kết hợp rating và residual thành đặc trưng 2 chiều
    combined_features = np.hstack((scaled_rating, scaled_residuals))

    # Phân cụm với KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    clusters = kmeans.fit_predict(combined_features)
    df['Cluster'] = clusters

    sil_score = silhouette_score(combined_features, clusters)
    return df, {
        "silhouette_score": sil_score,
        "inertia": kmeans.inertia_
    }


def recommend_one_day_trip(province, food_df, place_df, max_items=3):
    """
    Gợi ý cho 1 ngày dựa trên province.
    Trả về danh sách (food, places) với mỗi loại max_items (mặc định 3).
    Mỗi item được lấy theo rating cao nhất (không trùng 'title').
    """
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    recommended_food = (
        filtered_food.drop_duplicates(subset=['title'])
                     .nlargest(max_items, 'rating')[['title', 'rating', 'description', 'address', 'img']]
                     .to_dict('records')
    )

    recommended_places = (
        filtered_place.drop_duplicates(subset=['title'])
                      .nlargest(max_items, 'rating')[['title', 'rating', 'description', 'address', 'img']]
                      .to_dict('records')
    )

    return {"food": recommended_food, "places": recommended_places}


def get_recommendation_pool(province, food_df, place_df):
    """
    Lấy toàn bộ pool gợi ý (food, place) cho province (không trùng lặp, sắp xếp theo rating giảm dần).
    """
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    pool_food = (
        filtered_food.drop_duplicates(subset=['title'])
                     .sort_values(by='rating', ascending=False)[['title', 'rating', 'description', 'address', 'img']]
                     .to_dict('records')
    )
    pool_place = (
        filtered_place.drop_duplicates(subset=['title'])
                      .sort_values(by='rating', ascending=False)[['title', 'rating', 'description', 'address', 'img']]
                      .to_dict('records')
    )
    return {"food": pool_food, "places": pool_place}


def recommend_trip_schedule(start_day, end_day, province, food_df, place_df):
    """
    Tạo lịch trình nhiều ngày (start_day -> end_day) cho 1 province.
    Trong mỗi ngày, theo thứ tự các buổi:
      - Buổi sáng: recommend 1 món ăn và 1 nơi đi.
      - Buổi trưa: recommend 1 món ăn.
      - Buổi chiều: recommend 1 nơi đi.
      - Buổi tối: recommend 1 món ăn và 1 nơi đi dạo.
    Món ăn được chọn theo thứ tự (không lặp lại).
    Đối với địa điểm, trước tiên nhóm theo "district" (trích xuất từ address với district = parts[-3]),
    sau đó chọn địa điểm ngẫu nhiên từ các district chưa được dùng trong ngày nếu có đủ,
    nếu không thì chọn ngẫu nhiên từ tất cả các địa điểm còn lại.
    """
    fmt = "%Y-%m-%d"
    start = datetime.strptime(start_day, fmt)
    end = datetime.strptime(end_day, fmt)
    total_days = (end - start).days + 1
    if total_days < 1:
        return {"error": "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu."}

    # Lấy pool gợi ý
    pool = get_recommendation_pool(province, food_df, place_df)
    pool_food = pool.get("food", []).copy()
    pool_place = pool.get("places", []).copy()

    # Nhóm các địa điểm theo district (theo address)
    district_to_places = {}
    for item in pool_place:
        addr = item.get("address", "")
        parts = addr.split(", ")
        district = parts[-3] if len(parts) >= 3 else ""
        if district not in district_to_places:
            district_to_places[district] = []
        district_to_places[district].append(item)
    # Trộn ngẫu nhiên các danh sách trong mỗi district (để chọn random)
    for district in district_to_places:
        random.shuffle(district_to_places[district])

    # Hàm chọn địa điểm cho một buổi, ưu tiên lấy từ các district chưa dùng trong ngày
    def select_place(used_districts):
        # Danh sách các district còn chưa dùng có sẵn
        available_districts = [d for d, lst in district_to_places.items() if lst and d not in used_districts]
        if available_districts:
            # Chọn ngẫu nhiên 1 district từ available
            chosen_district = random.choice(available_districts)
            candidate = district_to_places[chosen_district].pop(0)
            used_districts.add(chosen_district)
            return candidate
        # Nếu không còn district chưa dùng, chọn ngẫu nhiên từ tất cả các district còn có địa điểm
        all_available = [(d, lst) for d, lst in district_to_places.items() if lst]
        if all_available:
            chosen_district, lst = random.choice(all_available)
            candidate = district_to_places[chosen_district].pop(0)
            used_districts.add(chosen_district)
            return candidate
        return {}

    # Hàm chọn món ăn (không lặp lại) theo thứ tự trong pool_food
    def select_food():
        if pool_food:
            return pool_food.pop(0)
        return {}

    schedule = []
    for i in range(total_days):
        current_day = start + pd.Timedelta(days=i)
        day_str = current_day.strftime(fmt)
        used_districts = set()  # reset cho mỗi ngày

        # Buổi sáng: 1 món ăn và 1 nơi đi
        morning_food = select_food()
        morning_place = select_place(used_districts)

        # Buổi trưa: 1 món ăn
        noon_food = select_food()

        # Buổi chiều: 1 nơi đi
        afternoon_place = select_place(used_districts)

        # Buổi tối: 1 món ăn và 1 nơi đi dạo
        evening_food = select_food()
        evening_place = select_place(used_districts)

        itinerary = [
            {"timeslot": "morning", "food": morning_food, "place": morning_place},
            {"timeslot": "noon", "food": noon_food},
            {"timeslot": "afternoon", "place": afternoon_place},
            {"timeslot": "evening", "food": evening_food, "place": evening_place}
        ]
        day_schedule = {
            "day": f"Day {i+1} ({day_str})",
            "itinerary": itinerary
        }
        schedule.append(day_schedule)

    return {
        "total_days": total_days,
        "start_day": start_day,
        "end_day": end_day,
        "province": province,
        "schedule": schedule
    }


def search_place(province):
    food_df, place_df = load_data(FOOD_FILE, PLACE_FILE)
    normalized_province = normalize_text(province)
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]
    food_list = filtered_food[['title', 'rating', 'description', 'address', 'img']].to_dict(orient='records')
    place_list = filtered_place[['title', 'rating', 'description', 'address', 'img']].to_dict(orient='records')
    return {
        "province": province,
        "food": food_list,
        "places": place_list
    }
