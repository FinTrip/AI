import os
import ast
import pandas as pd
import unidecode
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

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

    # Đổi tên cột cho food_df (ví dụ: 'Province' → 'province', 'Title' → 'title', …)
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

    # Xử lý cột 'rating' (nếu có)
    if 'rating' in food_df.columns:
        food_df['rating'] = pd.to_numeric(
            food_df['rating'].astype(str).str.replace(',', '.'),
            errors='coerce'
        )
        food_df.dropna(subset=['rating'], inplace=True)

    # Xử lý place_df
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
    """
    if df.empty:
        raise ValueError("Dataset is empty.")

    features = df[['rating']]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    df['Cluster'] = kmeans.fit_predict(scaled_features)

    return df, {
        "silhouette_score": silhouette_score(scaled_features, df['Cluster']),
        "inertia": kmeans.inertia_
    }


def recommend_one_day_trip(province, food_df, place_df, max_items=3):
    """
    Gợi ý cho 1 ngày dựa trên province.
    Trả về danh sách (food, places) với mỗi loại max_items (mặc định 3).
    Mỗi item (món ăn hoặc địa điểm) được lấy theo rating cao nhất (không trùng 'title').
    """
    normalized_province = normalize_text(province)

    # Lọc food/place theo province
    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    # Nếu rỗng => trả về
    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    # Lấy top max_items food
    recommended_food = (
        filtered_food
        .drop_duplicates(subset=['title'])
        .nlargest(max_items, 'rating')[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )

    # Lấy top max_items place
    recommended_places = (
        filtered_place
        .drop_duplicates(subset=['title'])
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
        filtered_food
        .drop_duplicates(subset=['title'])
        .sort_values(by='rating', ascending=False)[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )
    pool_place = (
        filtered_place
        .drop_duplicates(subset=['title'])
        .sort_values(by='rating', ascending=False)[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )
    return {"food": pool_food, "places": pool_place}


def recommend_trip_schedule(start_day, end_day, province, food_df, place_df):
    """
    Tạo lịch trình nhiều ngày (start_day -> end_day) cho 1 province.
    Mỗi món ăn, địa điểm chỉ xuất hiện 1 lần toàn lịch trình.
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

    schedule = []

    for i in range(total_days):
        current_day = start + pd.Timedelta(days=i)
        day_str = current_day.strftime(fmt)
        itinerary = []

        if i == 0:
            # Ngày đầu tiên: bỏ sáng
            # noon: 1 món ăn
            food_noon = pool_food.pop(0) if pool_food else {}
            # afternoon: 1 địa điểm
            place_afternoon = pool_place.pop(0) if pool_place else {}
            # evening: 1 món ăn + 1 địa điểm
            food_evening = pool_food.pop(0) if pool_food else {}
            place_evening = pool_place.pop(0) if pool_place else {}
            itinerary.append({"timeslot": "noon", "food": food_noon})
            itinerary.append({"timeslot": "afternoon", "place": place_afternoon})
            itinerary.append({"timeslot": "evening", "food": food_evening, "place": place_evening})
        elif i == total_days - 1:
            # Ngày cuối: bỏ chiều
            # morning: 1 món ăn + 1 địa điểm
            food_morning = pool_food.pop(0) if pool_food else {}
            place_morning = pool_place.pop(0) if pool_place else {}
            # noon: 1 món ăn
            food_noon = pool_food.pop(0) if pool_food else {}
            # evening: 1 món ăn + 1 địa điểm
            food_evening = pool_food.pop(0) if pool_food else {}
            place_evening = pool_place.pop(0) if pool_place else {}
            itinerary.append({"timeslot": "morning", "food": food_morning, "place": place_morning})
            itinerary.append({"timeslot": "noon", "food": food_noon})
            itinerary.append({"timeslot": "evening", "food": food_evening, "place": place_evening})
        else:
            # Ngày trung gian: full day
            # morning: 1 món ăn + 1 địa điểm
            food_morning = pool_food.pop(0) if pool_food else {}
            place_morning = pool_place.pop(0) if pool_place else {}
            # noon: 1 món ăn
            food_noon = pool_food.pop(0) if pool_food else {}
            # afternoon: 1 địa điểm
            place_afternoon = pool_place.pop(0) if pool_place else {}
            # evening: 1 món ăn + 1 địa điểm
            food_evening = pool_food.pop(0) if pool_food else {}
            place_evening = pool_place.pop(0) if pool_place else {}
            itinerary.append({"timeslot": "morning", "food": food_morning, "place": place_morning})
            itinerary.append({"timeslot": "noon", "food": food_noon})
            itinerary.append({"timeslot": "afternoon", "place": place_afternoon})
            itinerary.append({"timeslot": "evening", "food": food_evening, "place": place_evening})

        schedule.append({
            "day": f"Day {i + 1} ({day_str})",
            "itinerary": itinerary
        })

    return {
        "total_days": total_days,
        "start_day": start_day,
        "end_day": end_day,
        "province": province,
        "schedule": schedule
    }
