#image to text extraction using tesseract
import pytesseract
from PIL import Image
import os
from dotenv import load_dotenv

load_dotenv()
'''
# Configure Tesseract path (Windows-specific)
TESSERACT_PATH = os.getenv("TESSERACT_PATH")
if TESSERACT_PATH:
    pytesseract.pytesseract.pytesseract_cmd = TESSERACT_PATH
'''
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_text_from_image(image_path):
    """
    Extract text from an image using OCR (Tesseract).
    """
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from {image_path}: {e}")
        return ""

def extract_text_from_image_with_preprocessing(image_path):
    """
    Extract text from image with preprocessing (contrast, grayscale).
    Useful for handwritten notes or poor quality scans.
    """
    try:
        img = Image.open(image_path)
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Increase contrast for better OCR
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2)
        
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        print(f"Error with preprocessing: {e}")
        return ""

import pytesseract
from PIL import Image

def ocr_text_from_image(image_path):
    """
    Simple OCR extraction, returns text found in the image.
    """
    text = pytesseract.image_to_string(Image.open(image_path), config='--psm 6')
    return text


def ocr_from_image(image_path):
    """
    OCR using Tesseract for scanned images/handwriting.
    """
    return pytesseract.image_to_string(Image.open(image_path))
