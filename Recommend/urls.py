from django.urls import path,re_path
from . import views

app_name = 'Recommend'

urlpatterns = [
    #User
    path('create-user/', views.create_user, name='create_user'),
    path('login-user/', views.login_user, name='login_user'),
    path('delete-user/', views.delete_user, name='delete_user'),
    path('update-user/', views.update_user, name='update_user'),

    #Recommend travel
    path('rcm-travel/', views.recommend_travel_day, name='recommend_travel_day'),
    path('travel-schedule/', views.recommend_travel_schedule, name='recommend_travel_schedule'),
    path('save-schedule/', views.save_schedule, name='save_schedule'),

    #flight
    path('rcm-flight/', views.rcm_flight, name='rcm_flight'),
    path('select-flight/', views.select_flight, name='select_flight'),

    #Hotel show update delete
    path('rcm-hotel/', views.rcm_hotel, name='rcm_hotel'),
    path('update-hotel/', views.update_hotel, name='update_hotel'),
    path('delete-hotel/', views.delete_hotel, name='delete_hotel'),
    path('get-all-hotels/', views.get_all_hotels, name='get_all_hotels'),
    path('select_hotel/', views.select_hotel, name='select_hotel'),

    path('search-province/', views.search_province, name='search_province'),
    path('get-top-cities/', views.get_top_cities, name='get_top_cities'),
    path('search-place/', views.search_place, name='search_place'),
    path('search-food/', views.search_food, name='search_food'),

    #share schedule
    path('share-schedule/', views.share_schedule, name='share_schedule'),
    re_path(r'^view-schedule/(?P<share_token>[0-9a-f-]{36})/?$', views.view_schedule, name='view_schedule'),

    #Homepage
    path('homepage-hotels/', views.get_all_hotels_homepage, name='get_all_hotels_homepage'),
    path('homepage-place/', views.get_all_place_homepage, name='get_all_place_homepage'),
    path('select-place/', views.select_place, name='select_place'),
    path('homepage-food/', views.get_all_food_homepage, name='get_all_food_homepage'),
]