import os
import logging
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Đường dẫn tới thư mục chứa mô hình (model/Gptmodel1)
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'model', 'Gptmodel1'))

# Kiểm tra thư mục model/Gptmodel1
if not os.path.exists(MODEL_DIR):
    logging.error(f"Model directory '{MODEL_DIR}' not found. Please ensure the directory exists.")
    raise FileNotFoundError(f"Model directory '{MODEL_DIR}' not found.")

# Kiểm tra file safetensors
safetensors_file = os.path.join(MODEL_DIR, 'model-001.safetensors')
if not os.path.exists(safetensors_file):
    logging.error(f"Safetensors file '{safetensors_file}' not found in {MODEL_DIR}.")
    raise FileNotFoundError(f"Safetensors file 'model-001.safetensors' not found in {MODEL_DIR}.")

def load_model():
    try:
        logging.info("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
        logging.info("Tokenizer loaded successfully.")

        logging.info("Loading model...")
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

# Load model
model, tokenizer = load_model()

def chatbot_response(input_text):
    if model is None or tokenizer is None:
        logging.error("Model or tokenizer not loaded.")
        return "Error", 0.0, "Sorry, the system is currently experiencing issues. (Model not loaded)"

    try:
        prompt = f"question: {input_text}"
        inputs = tokenizer.encode(prompt, return_tensors="pt", max_length=512, truncation=True)

        outputs = model.generate(
            inputs,
            max_length=200,
            pad_token_id=tokenizer.eos_token_id,
            temperature=0.8,
            top_p=0.95,
            do_sample=True
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logging.info(f"Model response: {response}")
        predicted_class = "N/A"
        confidence = 0.0

        return predicted_class, confidence, response
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return "Error", 0.0, "Sorry, I cannot process your request at the moment."
