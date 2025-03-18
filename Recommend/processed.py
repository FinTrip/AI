import os
import ast
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

FOOD_FILE = os.path.join(os.path.dirname(__file__), "data", "food.csv")
PLACE_FILE = os.path.join(os.path.dirname(__file__), "data", "place.csv")


def safe_literal_eval(x):
    """
    Thực hiện ast.literal_eval an toàn.
    Nếu chuyển đổi thất bại, trả về danh sách rỗng.
    """
    try:
        return ast.literal_eval(x)
    except Exception:
        return []


def verify_file_path(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")


def load_data(food_path, place_path):
    # Kiểm tra sự tồn tại của file CSV
    verify_file_path(food_path)
    verify_file_path(place_path)

    # Đọc file CSV
    food_df = pd.read_csv(food_path)
    place_df = pd.read_csv(place_path)

    # -----------------------
    # 1) Xử lý food_df
    # -----------------------
    # Đổi tên các cột cho thống nhất (chuyển từ dạng viết hoa sang viết thường)
    rename_food_columns = {
        'Province': 'province',
        'Title': 'title',
        'Rating': 'rating',
        'Address': 'address',
        'Image': 'img'
    }
    food_df.rename(columns=rename_food_columns, inplace=True)

    # Nếu không có cột 'description' thì tạo cột đó với giá trị rỗng
    if 'description' not in food_df.columns:
        food_df['description'] = ''

    # Xử lý cột 'Service': chuyển thành cột 'types'
    if 'Service' in food_df.columns:
        food_df['types'] = food_df['Service'].apply(
            lambda x: safe_literal_eval(x) if pd.notnull(x) else []
        )
    else:
        food_df['types'] = [[] for _ in range(len(food_df))]

    # Xử lý cột 'rating'
    if 'rating' in food_df.columns:
        food_df['rating'] = pd.to_numeric(
            food_df['rating'].astype(str).str.replace(',', '.'),
            errors='coerce'
        )
        food_df.dropna(subset=['rating'], inplace=True)
    else:
        food_df['rating'] = float('nan')

    # -----------------------
    # 2) Xử lý place_df
    # -----------------------
    # place.csv đã có cột: province, title, rating, description, address, img, types
    if 'rating' in place_df.columns:
        place_df['rating'] = pd.to_numeric(
            place_df['rating'].astype(str).str.replace(',', '.'),
            errors='coerce'
        )
        place_df.dropna(subset=['rating'], inplace=True)
    else:
        place_df['rating'] = float('nan')

    # Nếu cột 'types' là chuỗi, chuyển thành list
    if 'types' in place_df.columns:
        place_df['types'] = place_df['types'].apply(
            lambda x: safe_literal_eval(x) if pd.notnull(x) else []
        )
    else:
        place_df['types'] = [[] for _ in range(len(place_df))]

    return food_df, place_df


def perform_clustering(df, n_clusters=5):
    if df.empty:
        raise ValueError("The dataset provided for clustering is empty.")

    features = df[['rating']]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    df['Cluster'] = kmeans.fit_predict(scaled_features)

    return df, {
        "silhouette_score": silhouette_score(scaled_features, df['Cluster']),
        "inertia": kmeans.inertia_
    }


def recommend_trip(location, food_df, place_df):
    """
    Lấy 5 món ăn và 5 địa điểm (có rating cao nhất) dựa trên province = location.
    """
    filtered_food = food_df[food_df['province'].str.contains(location, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(location, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    recommended_food = (
        filtered_food.nlargest(5, 'rating')[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )

    recommended_places = (
        filtered_place.nlargest(5, 'rating')[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )

    return {
        "food": recommended_food,
        "places": recommended_places
    }


def recommend_one_day_trip(province, food_df, place_df):
    """
    Lấy 3 món ăn và 3 địa điểm (có rating cao nhất) cho 1 chuyến đi 1 ngày dựa trên tên tỉnh.
    """
    filtered_food = food_df[food_df['province'].str.contains(province, case=False, na=False)]
    filtered_place = place_df[place_df['province'].str.contains(province, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    recommended_food = (
        filtered_food.nlargest(3, 'rating')[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )

    recommended_places = (
        filtered_place.nlargest(3, 'rating')[['title', 'rating', 'description', 'address', 'img']]
        .to_dict('records')
    )

    return {
        "food": recommended_food,
        "places": recommended_places
    }


def search_by_location(df, location):
    if 'province' not in df.columns or df['province'].isna().all():
        return []
    results = df[df['province'].str.contains(location, case=False, na=False)]
    return results.to_dict('records') if not results.empty else []


def search_by_key(df, key):
    if 'types' not in df.columns:
        return []
    results = df[df['types'].apply(lambda arr: any(key.lower() in t.lower() for t in arr) if arr else False)]
    return results.to_dict('records') if not results.empty else []


def search_by_location_and_key(df, location, key):
    if 'types' not in df.columns or 'province' not in df.columns:
        return []
    results = df[
        df['types'].apply(lambda arr: any(key.lower() in t.lower() for t in arr) if arr else False)
        & df['province'].str.contains(location, case=False, na=False)
        ]
    return results.to_dict('records') if not results.empty else []
