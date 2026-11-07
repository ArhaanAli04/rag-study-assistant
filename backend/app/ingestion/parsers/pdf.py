import fitz  # PyMuPDF

def extract_pdf_text(file_path):
    doc = fitz.open(file_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")  # simple text
        pages.append({
            "page_num": page_num + 1,
            "text": text
        })
    return pages

def extract_pdf_metadata(file_path):
    doc = fitz.open(file_path)
    meta = doc.metadata
    return {
        "title": meta.get("title"),
        "author": meta.get("author"),
        "creation_date": meta.get("creationDate")
    }

import pdfplumber

def extract_pdf_text_plumber(file_path):
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            pages.append({
                "page_num": i + 1,
                "text": text
            })
    return pages

def extract_pdf_multicolumn(file_path):
    doc = fitz.open(file_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        all_text = ''
        for b in sorted(blocks, key=lambda x: x[1]):  # sort by y position
            all_text += b[4] + '\n'
        pages.append({
            "page_num": page_num + 1,
            "text": all_text
        })
    return pages
