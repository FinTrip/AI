from django.urls import path
from . import views

app_name = 'Recommend'

urlpatterns = [
    path('rcm-travel/', views.recommend_travel_day, name='recommend_travel_day'),
    path('travel-schedule/', views.recommend_travel_schedule, name='recommend_travel_schedule'),
    path('save-schedule/', views.save_schedule, name='save_schedule'),
    path('rcm-flight/', views.rcm_flight, name='rcm_flight'),
    path('rcm-hotel/', views.rcm_hotel, name='rcm_hotel'),
]