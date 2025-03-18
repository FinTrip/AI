import os
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# Verify the existence of a file
def verify_file_path(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

# Load food and place datasets
def load_data(food_path, place_path):
    verify_file_path(food_path)
    verify_file_path(place_path)

    food_df = pd.read_csv(food_path)
    place_df = pd.read_csv(place_path)

    # Rename columns to English
    food_df.rename(columns={
        'STT': 'ID', 'Tên món ăn': 'Food Name', 'Vị trí': 'Location', 'Mô tả': 'Description',
        'Đánh giá': 'Rating', 'Ảnh': 'Image', 'Từ Khóa': 'Keywords'
    }, inplace=True)

    place_df.rename(columns={
        'STT': 'ID', 'Tên địa điểm': 'Place Name', 'Vị trí': 'Location', 'Mô tả': 'Description',
        'Đánh giá': 'Rating', 'Ảnh': 'Image', 'Từ Khóa': 'Keywords'
    }, inplace=True)

    # Process and clean ratings
    for df, name in [(food_df, 'Food'), (place_df, 'Place')]:
        if 'Rating' in df.columns:
            df['Rating'] = pd.to_numeric(
                df['Rating'].astype(str).str.replace(',', '.'),
                errors='coerce'
            )
            df.dropna(subset=['Rating'], inplace=True)
        else:
            df['Rating'] = float('nan')

    return food_df, place_df

# Perform clustering on a dataset
def perform_clustering(df, n_clusters=5):
    if df.empty:
        raise ValueError("The dataset provided for clustering is empty.")

    features = df[['Rating']]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    df['Cluster'] = kmeans.fit_predict(scaled_features)

    return df, {
        "silhouette_score": silhouette_score(scaled_features, df['Cluster']),
        "inertia": kmeans.inertia_
    }

# Recommend foods and places based on location
def recommend_trip(location, food_df, place_df):
    filtered_food = food_df[food_df['Location'].str.contains(location, case=False, na=False)]
    filtered_place = place_df[place_df['Location'].str.contains(location, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return {"food": [], "places": []}

    return {
        "food": filtered_food.nlargest(5, 'Rating').to_dict('records'),
        "places": filtered_place.nlargest(5, 'Rating').to_dict('records')
    }

# Search functionalities
def search_by_location(df, location):
    if 'Location' not in df.columns or df['Location'].isna().all():
        return []

    results = df[df['Location'].str.contains(location, case=False, na=False)]
    return results.to_dict('records') if not results.empty else []

def search_by_key(df, key):
    if 'Keywords' not in df.columns or df['Keywords'].isna().all():
        return []

    results = df[df['Keywords'].str.contains(key, case=False, na=False)]
    return results.to_dict('records') if not results.empty else []

def search_by_location_and_key(df, location, key):
    if 'Keywords' not in df.columns or 'Location' not in df.columns:
        return []

    results = df[
        df['Keywords'].str.contains(key, case=False, na=False) &
        df['Location'].str.contains(location, case=False, na=False)
    ]
    return results.to_dict('records') if not results.empty else []
