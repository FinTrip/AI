from django.shortcuts import render

from .processed import processed_data, recommend_trip
# Create your views here.
def recommendation_trip(request):
    processed_food, processed_place = processed_data()

    destination = "quảng nam"
    food_recommendations, place_recommendations = recommend_trip(destination, processed_food, processed_place)

    food_list = []
    # Print recommendations
    print("Food Recommendations:\n")
    for recommendation in food_recommendations:
        food_list.append(recommendation)

    place_list = []
    print("Place Recommendations:\n")
    for recommendation in place_recommendations:
        place_list.append(recommendation)

    return render(request, "Recommend/test.html", {"recommendations": place_list, "food_list":food_list})