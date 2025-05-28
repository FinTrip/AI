import google.generativeai as genai
import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import logging

# Thiết lập logger
logger = logging.getLogger(__name__)

# Cấu hình Gemini API
genai.configure(api_key="AIzaSyBY1Ik0rdmr9BlW1bHVreU6ltxQ4DWrUeo")  # Thay bằng API key của bạn
gemini_model = genai.GenerativeModel('gemini-2.0-flash')

# Đường dẫn và biến toàn cục
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model', 't5_small_model')
conversation_history = []

# Danh sách từ khóa để dùng T5 (hiện để rỗng để ưu tiên Gemini)
T5_KEYWORDS = []


# Load mô hình T5 và tokenizer
def load_model():
    if not os.path.exists(MODEL_DIR):
        logger.error(f"Thư mục mô hình không tồn tại: {MODEL_DIR}")
        return None, None
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR)
        model.eval()
        logger.info("Đã tải mô hình T5 thành công.")
        return model, tokenizer
    except Exception as e:
        logger.error(f"Lỗi khi tải mô hình: {e}")
        return None, None


model, tokenizer = load_model()


def clean_response(response):
    """Làm sạch phản hồi: loại bỏ ký hiệu và ngắt dòng không cần thiết."""
    # Loại bỏ các ký hiệu * và •
    response = response.replace('* ', '').replace('• ', '')
    # Loại bỏ các ngắt dòng không cần thiết, giữ lại sau câu hoàn chỉnh
    response = response.replace('\n', ' ').replace('. ', '.\n')
    # Loại bỏ khoảng trắng thừa
    response = ' '.join(response.split())
    return response.strip()


def get_gemini_response(input_text):
    """Tạo phản hồi từ Gemini dưới dạng một đoạn văn."""
    try:
        # Yêu cầu mô hình trả lời dưới dạng đoạn văn
        prompt = f"Cung cấp câu trả lời ngắn gọn dưới dạng một đoạn văn: {input_text}"
        response = gemini_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=300)
        )
        cleaned_response = clean_response(response.text.strip())
        return cleaned_response
    except Exception as e:
        logger.error(f"Lỗi Gemini: {e}")
        return "Không thể xử lý yêu cầu với Gemini."


def get_t5_response(input_text):
    """Tạo phản hồi từ T5 và làm sạch văn bản."""
    if model is None or tokenizer is None:
        logger.error("Mô hình T5 chưa được tải.")
        return "N/A", "Lỗi hệ thống."

    try:
        prompt = f"User: {input_text}\nAssistant:"
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)

        outputs = model.generate(
            inputs['input_ids'],
            attention_mask=inputs['attention_mask'],
            max_length=300,
            pad_token_id=tokenizer.pad_token_id,
            no_repeat_ngram_size=2,
            temperature=0.6,
            top_p=0.65,
            top_k=30,
            do_sample=True,
            early_stopping=True,
            num_beams=5
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # Kiểm tra và xử lý nếu phản hồi chứa prompt
        if response.lower().startswith(("user:", "assistant:")):
            response = "Xin lỗi, tôi không hiểu. Bạn có thể diễn đạt lại không?"

        cleaned_response = clean_response(response)
        return "N/A", cleaned_response
    except Exception as e:
        logger.error(f"Lỗi T5: {e}")
        return "N/A", "Không thể xử lý yêu cầu."


def chatbot_response(input_text):
    """Chọn mô hình và trả về phản hồi."""
    # Kiểm tra từ khóa để dùng T5
    if model is not None and tokenizer is not None and T5_KEYWORDS and any(
            keyword.lower() in input_text.lower() for keyword in T5_KEYWORDS):
        predicted_class, response = get_t5_response(input_text)
        return predicted_class, 0.0, response
    else:
        # Mặc định dùng Gemini
        response = get_gemini_response(input_text)
        return "N/A", 0.0, response