#image to text extraction using tesseract
from types import ModuleType

from PIL import Image

from app.core.config import settings


def _pytesseract() -> ModuleType:
    """Import pytesseract on first OCR call and point it at the configured binary.

    Not imported at module top: it costs ~2 s at import and every app start reaches this module
    through the PPTX pipeline, while only image slides and scans need it.
    """
    import pytesseract

    if settings.TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH
    return pytesseract

def extract_text_from_image(image_path):
    """
    Extract text from an image using OCR (Tesseract).
    """
    try:
        img = Image.open(image_path)
        text = _pytesseract().image_to_string(img)
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

        text = _pytesseract().image_to_string(img)
        return text.strip()
    except Exception as e:
        print(f"Error with preprocessing: {e}")
        return ""

def ocr_text_from_image(image_path):
    """
    Simple OCR extraction, returns text found in the image.
    """
    text = _pytesseract().image_to_string(Image.open(image_path), config='--psm 6')
    return text


def ocr_from_image(image_path):
    """
    OCR using Tesseract for scanned images/handwriting.
    """
    return _pytesseract().image_to_string(Image.open(image_path))
