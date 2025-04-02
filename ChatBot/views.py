from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .chatbot_model import chatbot_response
from .utils import logger
import time


@method_decorator(csrf_exempt, name='dispatch')
class ChatbotAPIView(APIView):
    """
    API endpoint để xử lý yêu cầu chatbot qua POST.
    """
    permission_classes = [AllowAny]

    def post(self, request, format=None):
        """
        Xử lý yêu cầu POST từ người dùng và trả về phản hồi từ chatbot.

        Args:
            request: Đối tượng HTTP request chứa dữ liệu JSON.
            format: Định dạng dữ liệu (không bắt buộc).

        Returns:
            Response: JSON chứa phản hồi hoặc thông báo lỗi.
        """
        start_time = time.time()  # Đo thời gian xử lý

        # Lấy dữ liệu từ request
        try:
            data = request.data
            if not isinstance(data, dict):
                logger.warning("Invalid request data: Not a dictionary.")
                return Response(
                    {"error": "Dữ liệu gửi lên phải là định dạng JSON."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            msg = data.get('text', '').strip()
            logger.info(f"Received user input: '{msg}'")

            if not msg:
                logger.warning("Empty input received.")
                return Response(
                    {"error": "Không có nội dung câu hỏi được cung cấp."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error parsing request data: {str(e)}", exc_info=True)
            return Response(
                {"error": "Lỗi khi đọc dữ liệu đầu vào."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Gọi hàm chatbot_response để sinh phản hồi
        try:
            predicted_class, confidence, bot_response_text = chatbot_response(msg)
            processing_time = time.time() - start_time
            logger.info(f"Response generated in {processing_time:.2f} seconds.")

            # Chuẩn bị phản hồi JSON
            response_data = {
                "status": "success" if predicted_class != "Error" else "error",
                "predicted_class": predicted_class,
                "confidence": confidence,
                "response": bot_response_text,
                "processing_time": f"{processing_time:.2f} seconds"
            }

            # Trả về phản hồi
            return Response(
                response_data,
                status=status.HTTP_200_OK if predicted_class != "Error" else status.HTTP_503_SERVICE_UNAVAILABLE
            )

        except Exception as e:
            logger.error(f"Unexpected error in view: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "error": "Hệ thống gặp lỗi không xác định.",
                    "details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )