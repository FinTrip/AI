import os.path
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# Load food and place data
def load_data(food_path, place_path):
    food_df = pd.read_excel(food_path)
    place_df = pd.read_excel(place_path)

    # Standardize column names
    food_df.columns = food_df.columns.str.strip()
    place_df.columns = place_df.columns.str.strip()

    # Print columns to verify
    print("Food DataFrame Columns:", food_df.columns)
    print("Place DataFrame Columns:", place_df.columns)

    # Rename columns to English
    food_df.rename(columns={
        'STT': 'ID', 'Tên món ăn': 'Food Name', 'Vị trí': 'Location', 'Mô tả': 'Description',
        'Đánh giá': 'Rating', 'Ảnh': 'Image', 'Từ Khóa': 'Keywords'
    }, inplace=True)

    place_df.rename(columns={
        'STT': 'ID', 'Tên địa điểm': 'Place Name', 'Vị trí': 'Location', 'Mô tả': 'Description',
        'Đánh giá': 'Rating', 'Ảnh': 'Image', 'Từ Khóa': 'Keywords'
    }, inplace=True)

    # Ensure 'Location' is the second column
    for df in [food_df, place_df]:
        if 'Location' in df.columns and df.columns.get_loc('Location') != 1:
            cols = df.columns.tolist()
            cols.insert(1, cols.pop(cols.index('Location')))
            df = df[cols]

    # Ensure 'Rating' column exists and handle format issues
    for df, name in [(food_df, 'Food'), (place_df, 'Place')]:
        if 'Rating' not in df.columns:
            print(f"Column 'Rating' does not exist in {name} dataset.")
            df['Rating'] = np.nan  # Add missing column with NaN values

        df.dropna(subset=['Rating'], inplace=True)
        df['Rating'] = df['Rating'].astype(str).str.replace(',', '.').str.extract(r'(\d+\.?\d*)').astype(float)

        # Drop empty rows
        df.dropna(how='all', inplace=True)

    return food_df, place_df

# Train KMeans model
def train_models(df, n_clusters=5, max_iter=100):
    if df.empty:
        raise ValueError("Dataset is empty after preprocessing.")

    features = df[['Rating']]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=max_iter)
    df['Cluster'] = kmeans.fit_predict(scaled_features)

    silhouette_avg = silhouette_score(scaled_features, df['Cluster'])
    inertia = kmeans.inertia_
    print(f"Silhouette Score: {silhouette_avg:.4f}")
    print(f"Inertia: {inertia:.4f}")

    return kmeans, scaler, df


# Recommend food and places
def recommend_trip(location, food_df, place_df):
    filtered_food = food_df[food_df['Location'].str.contains(location, case=False, na=False)]
    filtered_place = place_df[place_df['Location'].str.contains(location, case=False, na=False)]

    if filtered_food.empty or filtered_place.empty:
        return [], []

    # Sort by rating descending
    filtered_food = filtered_food.sort_values(by='Rating', ascending=False)
    filtered_place = filtered_place.sort_values(by='Rating', ascending=False)

    # Get all recommendations
    food_recommendations = [{
        "id": str(idx + 1),
        "name": row['Food Name'],
        "rating": float(row['Rating']),
        "description": row['Description'],
        "image": row['Image'],
        "location": row['Location'],
        "type": "FOOD"
    } for idx, row in filtered_food.iterrows()]

    place_recommendations = [{
        "id": str(idx + 1),
        "name": row['Place Name'],
        "rating": float(row['Rating']),
        "description": row['Description'],
        "image": row['Image'],
        "location": row['Location'],
        "type": "PLACE"
    } for idx, row in filtered_place.iterrows()]

    return food_recommendations, place_recommendations

def processed_data():
    food = os.path.join(os.path.dirname(__file__), "data", "food.xlsx")
    place = os.path.join(os.path.dirname(__file__), "data", "place.xlsx")
    food_data, place_data = load_data(food, place)

# Train models
    food_kmeans, food_scaler, processed_food = train_models(food_data)
    place_kmeans, place_scaler, processed_place = train_models(place_data)
    return processed_food, processed_place

place = os.path.join(os.path.dirname(__file__), "data", "place.xlsx")
df = pd.read_excel(place)

#recomnend location and key
def search_by_location(location):
    if 'Location' not in df.columns or df['Location'].isna().all():
        return []

    results = df[df['Location'].str.contains(location, case=False, na=False)]
    
    if results.empty:
        return []
        
    return [{
        "name": row['Place Name'],
        "rating": float(row['Rating']),
        "description": row['Description'],
        "image": row['Image'],
        "location": row['Location'],
        "keywords": row['Keywords']
    } for _, row in results.iterrows()]

def search_by_key(key):
    results = df[df['Keywords'].str.contains(key, case=False, na=False)]
    
    if results.empty:
        return []
        
    return [{
        "name": row['Place Name'],
        "rating": float(row['Rating']),
        "description": row['Description'],
        "image": row['Image'],
        "location": row['Location'],
        "keywords": row['Keywords']
    } for _, row in results.iterrows()]

def search_by_location_and_key(key, location):
    result = df[df['Keywords'].str.contains(key, case=False, na=False)]
    results = result[result['Location'].str.contains(location, case=False, na=False)]
    
    if results.empty:
        return []
        
    return [{
        "name": row['Place Name'],
        "rating": float(row['Rating']),
        "description": row['Description'],
        "image": row['Image'],
        "location": row['Location'],
        "keywords": row['Keywords']
    } for _, row in results.iterrows()]