from django.urls import path,re_path
from . import views

app_name = 'Recommend'

urlpatterns = [
    #User
    path('login-user/', views.login_user, name='login_user'),
    path('verify-token/', views.verify_token, name='verify_token'),

    ###
    #Schedule
    ###
    #Cache province and date
    path('start-survey/', views.start_survey, name='start_survey'),
    path('set-province/', views.set_province, name='set_province'),
    path('set-dates/', views.set_dates, name='set_dates'),
    path('set-budget/', views.set_budget, name='set_budget'),

    #flight
    path('check-flight-di/', views.check_flight_di, name='check_flight_di'),
    path('check-flight-den/', views.check_flight_den, name='check_flight_den'),
    path('rcm-flight/', views.rcm_flight, name='rcm_flight'),
    path('select-flight/', views.select_flight, name='select_flight'),

    #Hotel
    path('rcm-hotel/', views.rcm_hotel, name='rcm_hotel'),
    path('select_hotel/', views.select_hotel, name='select_hotel'),

    #recommend plan
    path('rcm-travel/', views.recommend_travel_day, name='recommend_travel_day'),
    path('travel-schedule/', views.recommend_travel_schedule, name='recommend_travel_schedule'),
    path('save-schedule/', views.save_schedule, name='save_schedule'),


    #share schedule
    path('share-schedule/', views.share_schedule, name='share_schedule'),
    path('share-schedule-via-email/', views.share_schedule_via_email, name='share_schedule_via_email'),
    re_path(r'^view-schedule/(?P<share_token>[0-9a-f-]{36})/?$', views.view_schedule, name='view_schedule'),

    #Homepage
    path('homepage-hotels/', views.get_all_hotels_homepage, name='get_all_hotels_homepage'),
    path('homepage-place/', views.get_all_place_homepage, name='get_all_place_homepage'),
    path('select-place/', views.select_place, name='select_place'),
    path('homepage-food/', views.get_all_food_homepage, name='get_all_food_homepage'),
    path('search-province/', views.search_province, name='search_province'),
    path('get-top-cities/', views.get_top_cities, name='get_top_cities'),
    path('search-place/', views.search_place, name='search_place'),
    path('search-food/', views.search_food, name='search_food'),

    #todolist
    path('todolist-create/', views.create_todolist_activity, name='create_todolist_activity'),
    path('todolist-get/', views.get_todolist_activities, name='get_todolist_activities'),
    path('todolist-update/', views.update_todolist_activities, name='get_todolist_activities'),
    path('todolist-delete/', views.delete_todolist_activities, name='delete_todolist_activities'),


    #Admin
    path('update-hotel/', views.update_hotel, name='update_hotel'),
    path('hotels/<str:name>/', views.get_hotel_by_name, name='get_hotel_by_name'),
    path('delete-hotel/', views.delete_hotel, name='delete_hotel'),
    path('get-all-hotels/', views.get_all_hotels, name='get_all_hotels'),
    path('search-hotels/', views.search_hotels_by_province, name='search_hotels_by_province'),


    path('delete-user/<int:user_id>/', views.delete_user, name='delete_user'),
    path('update-user/', views.update_user, name='update_user'),
    path('create-user/', views.create_user, name='create_user'),
    path('user-management/', views.user_manage, name='user_manage'),
    path('user/<int:user_id>/', views.get_user, name='get_user'),
    path('search-user/', views.search_user, name='search_user'),
    path('filter-role-user/', views.filter_by_role, name='filter_by_role'),
    path('filter-status-user/', views.filter_by_status, name='filter_by_status'),

    #Place
    path('get-place-admin/', views.get_all_place_admin, name='get_all_place_admin'),
    path('add-place/', views.add_place, name='add_place'),
    path('delete-place/', views.delete_place, name='delete_place'),
    path('update-place/', views.update_place, name='update_place'),
    #Food
    path('get-food-admin/', views.get_all_food_admin, name='get_all_food_admin'),
    path('add-food/', views.add_food, name='add_food'),
    path('delete-food/', views.delete_food, name='delete_food'),
    path('update-food/', views.update_food, name='update_food'),
]