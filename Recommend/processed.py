import os
import ast
import pandas as pd
import json
import datetime
import unidecode
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# Đường dẫn cố định đến file dữ liệu
FOOD_FILE = os.path.join(os.path.dirname(__file__), "data", "food.csv")
PLACE_FILE = os.path.join(os.path.dirname(__file__), "data", "place.csv")


def normalize_text(text):
    """Chuẩn hóa văn bản: viết thường, loại bỏ khoảng trắng, không phân biệt dấu."""
    if isinstance(text, str):
        return unidecode.unidecode(text.lower().strip())
    return ""


def safe_literal_eval(x):
    """Chuyển đổi chuỗi thành danh sách, nếu lỗi trả về danh sách rỗng."""
    try:
        return ast.literal_eval(x) if isinstance(x, str) else []
    except (ValueError, SyntaxError):
        return []


def verify_file_path(path):
    """Kiểm tra file có tồn tại không."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")


def load_data(food_path, place_path):
    """Đọc dữ liệu từ CSV và xử lý."""
    verify_file_path(food_path)
    verify_file_path(place_path)

    food_df = pd.read_csv(food_path)
    place_df = pd.read_csv(place_path)

    # Chuẩn hóa tên cột
    rename_food_columns = {
        'Province': 'province',
        'Title': 'title',
        'Rating': 'rating',
        'Address': 'address',
        'Image': 'img'
    }
    food_df.rename(columns=rename_food_columns, inplace=True)

    if 'description' not in food_df.columns:
        food_df['description'] = ''

    if 'Service' in food_df.columns:
        food_df['types'] = food_df['Service'].apply(safe_literal_eval)
    else:
        food_df['types'] = [[] for _ in range(len(food_df))]

    if 'rating' in food_df.columns:
        food_df['rating'] = pd.to_numeric(food_df['rating'].astype(str).str.replace(',', '.'), errors='coerce')
        food_df.dropna(subset=['rating'], inplace=True)

    if 'rating' in place_df.columns:
        place_df['rating'] = pd.to_numeric(place_df['rating'].astype(str).str.replace(',', '.'), errors='coerce')
        place_df.dropna(subset=['rating'], inplace=True)

    if 'types' in place_df.columns:
        place_df['types'] = place_df['types'].apply(safe_literal_eval)
    else:
        place_df['types'] = [[] for _ in range(len(place_df))]

    # Chuẩn hóa dữ liệu
    food_df['province'] = food_df['province'].apply(normalize_text)
    place_df['province'] = place_df['province'].apply(normalize_text)

    return food_df, place_df


def perform_clustering(df, n_clusters=5):
    """Thực hiện phân cụm dựa trên `rating`."""
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


def recommend_one_day_trip(province, food_df, place_df):
    """Gợi ý món ăn và địa điểm dựa trên tỉnh thành."""
    normalized_province = normalize_text(province)

    filtered_food = food_df[food_df['province'].str.contains(normalized_province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(normalized_province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    # Loại bỏ trùng lặp
    recommended_food = filtered_food.drop_duplicates(subset=['title']).nlargest(3, 'rating')[
        ['title', 'rating', 'description', 'address', 'img']].to_dict('records')

    recommended_places = filtered_place.drop_duplicates(subset=['title']).nlargest(3, 'rating')[
        ['title', 'rating', 'description', 'address', 'img']].to_dict('records')

    return {"food": recommended_food, "places": recommended_places}
