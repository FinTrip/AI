import os
import logging
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Path to the model directory
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'File', 'Gptmodel2version0.h5')

def load_model():
    """
    Load the tokenizer and trained model from the specified directory.

    Returns:
        tuple: A tuple containing the model and tokenizer.
    """
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR, trust_remote_code=True)
        model.eval()
        logging.info("Model and tokenizer loaded successfully.")
        return model, tokenizer
    except Exception as e:
        logging.error(f"Error loading model: {e}")
        return None, None

# Load the model and tokenizer when the module is imported
model, tokenizer = load_model()

def chatbot_response(input_text):
    """
    Generate a response from the trained model with fixed configuration parameters.

    Parameters:
        input_text (str): The user's input text.

    Returns:
        tuple: A tuple containing predicted_class, confidence, and response_text.
    """
    if model is None or tokenizer is None:
        logging.error("Model or tokenizer not loaded.")
        return "Error", 0.0, "Sorry, the system is currently experiencing issues."

    try:
        # For Seq2Seq models like T5, use a prefix to guide the task
        prompt = f"question: {input_text}"

        inputs = tokenizer.encode(prompt, return_tensors="pt", max_length=512, truncation=True)
        attention_mask = torch.ones(inputs.shape, dtype=torch.long)  # Tạo attention mask với cùng kích thước

        outputs = model.generate(
            inputs,
            attention_mask=attention_mask,  # Truyền attention mask
            max_length=200,              # Tăng độ dài tối đa của phản hồi
            pad_token_id=tokenizer.eos_token_id,
            no_repeat_ngram_size=2,      # Không lặp lại n-grams
            temperature=0.8,             # Điều chỉnh nhiệt độ để tăng độ sáng tạo
            top_p=0.95,                  # Tăng Top-p để chọn các từ có xác suất cao nhất
            top_k=50,                    # Giữ nguyên Top-k
            do_sample=True,              # Kích hoạt chế độ lấy mẫu
            num_beams=5,                 # Sử dụng beam search với 5 beams
            early_stopping=True          # Dừng sớm khi đạt được phản hồi hợp lý
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logging.info(f"Model response: {response}")

        # Since transformers do not provide predicted_class and confidence,
        # we'll return 'N/A' and 0.0 respectively.
        predicted_class = "N/A"
        confidence = 0.0

        return predicted_class, confidence, response
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return "Error", 0.0, "Sorry, I cannot process your request at the moment."
