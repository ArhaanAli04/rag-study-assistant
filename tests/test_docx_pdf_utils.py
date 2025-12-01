import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from pdf_table_utils import extract_tables_camelot, extract_tables_pdfplumber
from ocr_utils import ocr_from_image
from docx_utils import extract_docx_content
from image_preprocessing import preprocess_image,preprocess_image_extra
from unified_parser import DocumentParser

def test_pdf_table_extraction():
    pdf_path = "tests/samples/table_test.pdf"
    if os.path.exists(pdf_path):
        tables = extract_tables_camelot(pdf_path)
        print("Camelot Tables Found:", len(tables))
        if not tables:
            tables = extract_tables_pdfplumber(pdf_path)
            print("pdfplumber Tables Found:", len(tables))
        assert isinstance(tables, list)

def test_image_ocr_preprocess():
    img_path = "tests/samples/scan_handwritten.png"
    if os.path.exists(img_path):
        processed = preprocess_image_extra(img_path)
        text = ocr_from_image(processed)
        print("OCR Text:", text)
        assert isinstance(text, str)

def test_docx_extraction():
    docx_path = "tests/samples/test_style.docx"
    if os.path.exists(docx_path):
        content = extract_docx_content(docx_path)
        print("DOCX Content:", content[:2])  # Print first two paragraphs
        assert isinstance(content, list)

def test_unified_parser_pdf():
    pdf_path = "tests/samples/table_test.pdf"
    if os.path.exists(pdf_path):
        parser = DocumentParser(pdf_path)
        result = parser.parse()
        print("Unified PDF Parse:", result)

def test_unified_parser_image():
    img_path = "tests/samples/scan_handwritten.png"
    if os.path.exists(img_path):
        parser = DocumentParser(img_path)
        result = parser.parse()
        print("Unified Image Parse:", result)

def test_unified_parser_docx():
    docx_path = "tests/samples/test_style.docx"
    if os.path.exists(docx_path):
        parser = DocumentParser(docx_path)
        result = parser.parse()
        print("Unified DOCX Parse:", result)
