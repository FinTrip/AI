import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Đường dẫn tới thư mục mô hình
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model', '')

# Lịch sử hội thoại toàn cục (có thể thay bằng cơ chế lưu trữ khác nếu cần)
conversation_history = []


def load_model():
    """Tải mô hình và tokenizer từ thư mục đã chỉ định."""
    if not os.path.exists(MODEL_DIR):
        print(f"Lỗi: Thư mục mô hình không tồn tại: {MODEL_DIR}")
        return None, None
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR, trust_remote_code=True)
        model.eval()
        return model, tokenizer
    except Exception as e:
        print(f"Lỗi khi tải mô hình: {e}")
        return None, None


# Tải mô hình và tokenizer khi module được import
model, tokenizer = load_model()


def chatbot_response(input_text):
    """Tạo phản hồi từ chatbot dựa trên đầu vào của người dùng."""
    global conversation_history

    if model is None or tokenizer is None:
        return "Error", 0.0, "Xin lỗi, hệ thống hiện đang gặp sự cố."

    try:
        # Thêm câu hỏi mới vào lịch sử hội thoại
        conversation_history.append(f"User: {input_text}")

        # Giới hạn độ dài lịch sử để tránh vượt quá giới hạn token
        if len(conversation_history) > 10:  # Giữ 10 lượt hội thoại gần nhất
            conversation_history = conversation_history[-10:]

        # Tạo prompt bao gồm lịch sử hội thoại
        prompt = " ".join(conversation_history) + " Assistant:"

        # Mã hóa prompt
        inputs = tokenizer.encode(prompt, return_tensors="pt", max_length=512, truncation=True)

        # Tạo phản hồi với các tham số đã điều chỉnh
        outputs = model.generate(
            inputs,
            max_length=100,
            pad_token_id=tokenizer.eos_token_id,
            no_repeat_ngram_size=2,  # Tăng lên 2 để tránh lặp từ không tự nhiên
            temperature=0.6,  # Giảm để tăng tính chính xác
            top_p=0.85,  # Điều chỉnh để cân bằng sáng tạo và chính xác
            top_k=40,  # Điều chỉnh để hạn chế lựa chọn từ
            do_sample=True,
            early_stopping=True,
            num_beams=5  # Tăng num_beams để sử dụng beam search, tránh cảnh báo
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Thêm phản hồi vào lịch sử hội thoại
        conversation_history.append(f"Assistant: {response}")

        return "N/A", 0.0, response
    except Exception as e:
        print(f"Lỗi khi tạo phản hồi: {e}")
        return "Error", 0.0, "Xin lỗi, tôi không thể xử lý yêu cầu của bạn lúc này."