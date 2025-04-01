import os
import logging
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Cấu hình logging để dễ theo dõi
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Xác định đường dẫn tới model dựa trên cấu trúc thư mục hiện tại
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model', 'Gptmodelx1')
if not os.path.exists(MODEL_DIR):
    logging.error(f"Model directory '{MODEL_DIR}' not found. Please check the model path.")


def load_model():
    try:
        logging.info("Loading tokenizer...")
        # Dùng trust_remote_code=True nếu model yêu cầu chạy code từ remote
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
        logging.info("Tokenizer loaded successfully.")

        logging.info("Loading model...")
        # Chọn torch_dtype dựa trên việc có GPU hay không
        model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_DIR,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        model.eval()
        logging.info("Model loaded successfully.")
        return model, tokenizer
    except Exception as e:
        logging.error(f"Error loading model/tokenizer: {e}")
        return None, None


# Load model khi module được import
model, tokenizer = load_model()


def chatbot_response(input_text):
    if model is None or tokenizer is None:
        logging.error("Model or tokenizer not loaded.")
        return "Error", 0.0, "Sorry, the system is currently experiencing issues. (Model not loaded)"

    try:
        prompt = f"question: {input_text}"
        # Mã hóa input với giới hạn độ dài 512 tokens và tạo attention mask
        inputs = tokenizer.encode(prompt, return_tensors="pt", max_length=512, truncation=True)
        attention_mask = torch.ones(inputs.shape, dtype=torch.long)

        outputs = model.generate(
            inputs,
            attention_mask=attention_mask,
            max_length=200,
            pad_token_id=tokenizer.eos_token_id,
            no_repeat_ngram_size=2,
            temperature=0.8,
            top_p=0.95,
            top_k=50,
            do_sample=True,
            num_beams=5,
            early_stopping=True
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logging.info(f"Model response: {response}")
        predicted_class = "N/A"
        confidence = 0.0

        return predicted_class, confidence, response
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return "Error", 0.0, "Sorry, I cannot process your request at the moment."
