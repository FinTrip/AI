from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .chatbot_model import chatbot_response
import logging

# Thiết lập logger
logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class ChatbotAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, format=None):
        try:
            data = request.data
            msg = data.get('text', '').strip()
            if not msg:
                logger.warning("No message provided.")
                return Response({"error": "Không có tin nhắn nào được cung cấp."},
                              status=status.HTTP_400_BAD_REQUEST)

            # Gọi hàm chatbot_response
            predicted_class, confidence, bot_response_text = chatbot_response(msg)

            # Kiểm tra nếu phản hồi từ chatbot là None hoặc rỗng
            if not bot_response_text:
                logger.error("Chatbot response is empty.")
                return Response({"error": "Không thể nhận phản hồi từ chatbot."},
                              status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({
                "predicted_class": predicted_class,
                "confidence": confidence,
                "response": bot_response_text
            }, status=status.HTTP_200_OK)
        except KeyError as e:
            logger.error(f"KeyError in view: {e}")
            return Response({"error": "Dữ liệu yêu cầu không hợp lệ."},
                          status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error in view: {e}")
            return Response({"error": "Lỗi server nội bộ"},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)