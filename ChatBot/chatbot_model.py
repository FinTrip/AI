import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Path to the model directory
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model', 'T5_vn_finetuned_model2')

def load_model():
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR, trust_remote_code=True)
        model.eval()
        return model, tokenizer
    except Exception as e:
        print(f"Error loading model: {e}") # Print error to console instead of logging
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
        print("Model or tokenizer not loaded.") # Print error to console instead of logging
        return "Error", 0.0, "Sorry, the system is currently experiencing issues."

    try:
        # For Seq2Seq models like T5, use a prefix to guide the task
        prompt = f"question: {input_text}"

        inputs = tokenizer.encode(prompt, return_tensors="pt", max_length=512, truncation=True)

        outputs = model.generate(
            inputs,
            max_length=100,             # Maximum length of the response
            pad_token_id=tokenizer.eos_token_id,
            no_repeat_ngram_size=1,      # Do not repeat n-grams
            temperature=0.7,             # Temperature
            top_p=0.9,                   # Top-p (Nucleus Sampling)
            top_k=50,                    # Top-k
            do_sample=True,
            early_stopping=True
        )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print(f"Model response: {response}") # Print response to console instead of logging

        # Since transformers do not provide predicted_class and confidence,
        # we'll return 'N/A' and 0.0 respectively.
        predicted_class = "N/A"
        confidence = 0.0

        return predicted_class, confidence, response
    except Exception as e:
        print(f"Error generating response: {e}") # Print error to console instead of logging
        return "Error", 0.0, "Sorry, I cannot process your request at the moment."