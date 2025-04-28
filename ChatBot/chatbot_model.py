import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch
from sentence_transformers import SentenceTransformer, util

# Đường dẫn tới thư mục mô hình
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model', 't5_small_model')

# Lịch sử hội thoại toàn cục (có thể thay bằng cơ chế lưu trữ khác nếu cần)
conversation_history = []

# Tải SentenceTransformer để đo độ liên quan
similarity_model = SentenceTransformer('all-MiniLM-L6-v2')

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
    """Tạo phản hồi từ chatbot cho từng câu hỏi riêng biệt."""
    if model is None or tokenizer is None:
        return "Error", 0.0, "Xin lỗi, hệ thống đang gặp sự cố."

    try:
        prompt = f"User: {input_text}\nAssistant:"
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)

        outputs = model.generate(
            inputs['input_ids'],
            attention_mask=inputs['attention_mask'],
            max_length=300,
            pad_token_id=tokenizer.eos_token_id,
            no_repeat_ngram_size=2,
            temperature=0.9,
            top_p=0.95,
            top_k=30,
            do_sample=True,
            early_stopping=True,
            num_beams=5
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # Nếu model trả về prompt
        if response.lower().startswith("user:") or response.lower().startswith("assistant:"):
            response = "Xin lỗi, tôi chưa hiểu yêu cầu của bạn. Bạn có thể hỏi lại được không?"
            return "N/A", 0.0, response

        # Kiểm tra độ tương đồng giữa input và output
        embeddings = similarity_model.encode([input_text, response], convert_to_tensor=True)
        similarity_score = util.pytorch_cos_sim(embeddings[0], embeddings[1]).item()

        # Nếu độ tương đồng quá thấp (<0.5), coi như model trả lời sai
        if similarity_score < 0.5:
            response = "Xin lỗi, tôi chưa hiểu rõ yêu cầu của bạn. Bạn có thể hỏi lại chi tiết hơn không?"

        return "N/A", similarity_score, response

    except Exception as e:
        print(f"Lỗi khi tạo phản hồi: {e}")
        return "Error", 0.0, "Xin lỗi, tôi không thể xử lý yêu cầu của bạn lúc này."
