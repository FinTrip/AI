from django.urls import path
from . import views
app_name = 'Recommend'
urlpatterns = [
    path('', views.recommendation_trip, name='recommendation_trip'),
]