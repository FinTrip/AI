from django.urls import path
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

    #Hotel show update delete
    path('rcm-hotel/', views.rcm_hotel, name='rcm_hotel'),
    path('update-hotel/', views.update_hotel, name='update_hotel'),
    path('delete-hotel/', views.delete_hotel, name='delete_hotel'),
    path('get-all-hotels/', views.get_all_hotels, name='get_all_hotels'),

    path('search-province/', views.search_province, name='search_province'),

    #share schedule
    path('share-schedule/', views.share_schedule, name='share_schedule'),
    path('view-schedule/<int:schedule_id>/', views.view_schedule, name='view_schedule'),
]