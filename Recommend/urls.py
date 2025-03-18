from django.urls import path
from . import views

app_name = 'Recommend'

urlpatterns = [
    path('rcm-travel/', views.recommend_travel_day, name='rcmtravel'),
    path('rcm-travel-schedule/', views.recommend_travel_schedule, name='rcmtraveleshedule'),
    path('rcm-flight/', views.rcm_flight, name='rcmflight'),
    path('rcm-hotel/', views.rcm_hotel, name='rcmhotel'),
]
