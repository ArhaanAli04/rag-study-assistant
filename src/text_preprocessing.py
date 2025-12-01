#normalize text
import re
import string

def normalize_text(text):
    """
    Normalize extracted text by:
    - Removing extra whitespace
    - Fixing common OCR errors
    - Standardizing punctuation
    """
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters but keep punctuation
    text = re.sub(r'[^\w\s\.\,\!\?\-\:\;\']', '', text)
    
    # Fix common OCR errors (l -> I, O -> 0, etc.)
    text = fix_ocr_errors(text)
    
    return text.strip()

def fix_ocr_errors(text):
    """
    Fix common OCR misrecognitions.
    """
    replacements = {
        r'\bl\b': 'I',  # Single 'l' to 'I' (context-specific)
        r'O(\d)': r'\1',  # 'O' before digits to nothing
        r'(\d)O': r'\1',  # Digit followed by 'O' to digit
        r'rn': 'm',  # 'rn' might be 'm'
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text

def remove_boilerplate(text):
    """
    Remove common boilerplate text like page numbers, headers, footers.
    """
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        # Skip lines that are just page numbers
        if not re.match(r'^[\d\-\s]*$', line):
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines).strip()

def clean_text(text):
    """
    Master function that applies all cleaning operations.
    """
    text = normalize_text(text)
    text = remove_boilerplate(text)
    return text
