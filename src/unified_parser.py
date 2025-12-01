import os
from pdf_utils import extract_pdf_text, extract_pdf_metadata
from pdf_table_utils import extract_tables_camelot, extract_tables_pdfplumber
from ocr_utils import ocr_from_image
from docx_utils import extract_docx_content
from image_preprocessing import preprocess_image

class DocumentParser:
    def __init__(self, path):
        self.path = path
        self.ext = os.path.splitext(path)[-1].lower()

    def parse(self):
        if self.ext == '.pdf':
            # PDF text and tables
            text = extract_pdf_text(self.path)
            tables = extract_tables_camelot(self.path)
            if not tables:
                tables = extract_tables_pdfplumber(self.path)
            return {'type': 'pdf', 'text': text, 'tables': tables}
        elif self.ext in ['.png', '.jpg', '.jpeg']:
            # Image OCR and preprocessing
            p_img = preprocess_image(self.path)
            text = ocr_from_image(p_img)
            return {'type': 'image', 'text': text}
        elif self.ext == '.docx':
            # DOCX style-preserved extraction
            content = extract_docx_content(self.path)
            return {'type': 'docx', 'content': content}
        else:
            raise ValueError(f"Unsupported file extension: {self.ext}")
