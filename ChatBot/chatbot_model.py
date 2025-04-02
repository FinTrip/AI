import os
import logging
from .utils import logger  # Sử dụng logger từ utils.py

logger.info("Starting chatbot_model.py import process...")

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    logger.info("Successfully imported torch and transformers.")
except ImportError as e:
    logger.error(f"Failed to import required libraries: {str(e)}")
    raise

# Đường dẫn tương đối tới mô hình đã huấn luyện
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model', 'Gptmodel1')
logger.info(f"Model directory set to: {MODEL_DIR}")

# Biến toàn cục
model = None
tokenizer = None


def load_model():
    """
    Tải mô hình và tokenizer từ thư mục cục bộ.
    """
    global model, tokenizer
    logger.debug(f"Starting load_model() with MODEL_DIR: {MODEL_DIR}")

    try:
        logger.info(f"Checking if model directory exists: {MODEL_DIR}")
        if not os.path.exists(MODEL_DIR):
            logger.error(f"Model directory does not exist: {MODEL_DIR}")
            raise FileNotFoundError(f"Model directory '{MODEL_DIR}' not found.")

        # Kiểm tra file trọng số
        weight_files = ['pytorch_model.bin', 'model.safetensors']
        has_weights = any(os.path.exists(os.path.join(MODEL_DIR, f)) for f in weight_files)
        if not has_weights:
            logger.error(f"No weight files (pytorch_model.bin or model.safetensors) found in {MODEL_DIR}")
            raise FileNotFoundError(f"No model weights found in {MODEL_DIR}")

        # Kiểm tra các file cấu hình và tokenizer
        required_files = ['config.json', 'tokenizer.json']
        for file_name in required_files:
            file_path = os.path.join(MODEL_DIR, file_name)
            logger.debug(f"Checking file: {file_path}")
            if not os.path.exists(file_path):
                logger.error(f"Required file missing: {file_path}")
                raise FileNotFoundError(f"File '{file_name}' not found in {MODEL_DIR}")

        # Tải tokenizer
        logger.info(f"Loading tokenizer from {MODEL_DIR}...")
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_DIR,
            use_fast=True,
            trust_remote_code=True
        )
        logger.info("Tokenizer loaded successfully.")

        # Tải mô hình
        logger.info(f"Loading model from {MODEL_DIR}...")
        model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_DIR,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            trust_remote_code=True
        )

        if torch.cuda.is_available():
            logger.info("Moving model to GPU...")
            model = model.cuda()
            logger.debug(f"Using device: {torch.cuda.current_device()} - {torch.cuda.get_device_name()}")
        else:
            logger.info("Using CPU for model inference.")

        model.eval()
        logger.info("Model loaded successfully.")
        return model, tokenizer
    except Exception as e:
        logger.error(f"Failed to load model or tokenizer: {str(e)}", exc_info=True)
        return None, None


logger.info("Initializing model loading process...")
model, tokenizer = load_model()
if model is None or tokenizer is None:
    logger.critical("Model initialization failed. Chatbot will not function properly.")


def chatbot_response(input_text):
    """
    Sinh phản hồi từ mô hình dựa trên input của người dùng.

    Args:
        input_text (str): Văn bản đầu vào từ người dùng.

    Returns:
        tuple: (predicted_class, confidence, response_text)
    """
    logger.info(f"Processing user input: '{input_text}'")

    if not isinstance(input_text, str) or not input_text.strip():
        logger.warning("Invalid input: Empty or non-string input received.")
        return "Error", 0.0, "Vui lòng nhập một câu hỏi hợp lệ."

    if model is None or tokenizer is None:
        logger.error("Cannot generate response: Model or tokenizer not loaded.")
        return "Error", 0.0, "Hệ thống đang gặp sự cố. Vui lòng thử lại sau."

    try:
        logger.debug("Encoding input text...")
        inputs = tokenizer(
            input_text,
            return_tensors="pt",
            max_length=128,
            truncation=True,
            padding="max_length"
        )

        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
            logger.debug("Input tensors moved to GPU.")

        logger.debug("Generating response with model...")
        outputs = model.generate(
            **inputs,
            max_length=128,
            pad_token_id=tokenizer.eos_token_id,
            temperature=0.7,
            top_p=0.9,
            top_k=50,
            do_sample=True,
            num_beams=1
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logger.info(f"Generated response: '{response}'")
        return "Positive", 0.95, response

    except Exception as e:
        logger.error(f"Error during response generation: {str(e)}", exc_info=True)
        return "Error", 0.0, "Không thể tạo phản hồi. Vui lòng thử lại."