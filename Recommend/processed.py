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
        return {"Message": "No suitable locations found."}

    # Sort by rating descending
    filtered_food = filtered_food.sort_values(by='Rating', ascending=False)
    filtered_place = filtered_place.sort_values(by='Rating', ascending=False)

    unique_foods = filtered_food.drop_duplicates(subset=['Food Name']).head(3)
    unique_places = filtered_place.drop_duplicates(subset=['Place Name']).head(2)

    food_recommendations = []
    for i, row in unique_foods.iterrows():
        food_recommendations.append(f"{row['Food Name']}\n\nRating: {row['Rating']}\n\nDescription: {row['Description']}\n")

    place_recommendations = []
    for i, row in unique_places.iterrows():
        place_recommendations.append(f"{row['Place Name']}\n\nRating: {row['Rating']}\n\nDescription: {row['Description']}\n")

    return food_recommendations, place_recommendations

def processed_data():
    food = os.path.join(os.path.dirname(__file__), "data", "food.xlsx")
    place = os.path.join(os.path.dirname(__file__), "data", "place.xlsx")
    food_data, place_data = load_data(food, place)

# Train models
    food_kmeans, food_scaler, processed_food = train_models(food_data)
    place_kmeans, place_scaler, processed_place = train_models(place_data)
    return processed_food, processed_place

