from django.urls import path
from . import views

app_name = 'Recommend'

urlpatterns = [
    path('rcm-travel/', views.RCMTravelDay.as_view(), name='rcmtravel'),
    path('rcm-location-key/', views.RCMLocationAndKeywords.as_view(), name='rcmlocationkey'),
]