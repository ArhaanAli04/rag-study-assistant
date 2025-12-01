import re

def chunk_text(text, chunk_size=1000, overlap=100):
    # Split into paragraphs, then stitch into token-sized chunks
    paragraphs = [p for p in text.split('\n') if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += para + "\n"
        else:
            chunks.append(current.strip())
            # Start new chunk with overlap from last chunk
            current = current[-overlap:] + para + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks

from pdf_utils import extract_pdf_text,extract_pdf_metadata


def chunk_pdf(file_path):
    pages = extract_pdf_text(file_path)
    all_chunks = []
    for page in pages:
        page_num = page["page_num"]
        text = page["text"]
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "page_num": page_num,
                "chunk_num": i + 1,
                "text": chunk
            })
    return all_chunks


def chunk_pptx(file_path):
    """
    Process PPTX file and return chunked data with metadata.
    """
    from pptx_pipeline import process_pptx
    
    processed = process_pptx(file_path)
    all_chunks = []
    
    for slide in processed["slides"]:
        for chunk_data in slide["chunks"]:
            all_chunks.append({
                "slide_num": slide["slide_num"],
                "slide_title": slide["title"],
                "chunk_num": chunk_data["chunk_num"],
                "text": chunk_data["text"]
            })
    
    return all_chunks
