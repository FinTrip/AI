from django.urls import path
from .views import ChatbotAPIView
app_name = 'ChatBot'

urlpatterns = [
    path('chat/', ChatbotAPIView.as_view(), name='chatbot_api'),
]
