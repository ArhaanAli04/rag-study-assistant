#complete PPTX processing pipeline
from pptx_utils import extract_pptx_text, extract_pptx_metadata
from ocr_utils import extract_text_from_image_with_preprocessing
from table_utils import extract_tables_from_pptx_slides
from text_preprocessing import clean_text
from chunking import chunk_text

def process_pptx(file_path):
    """
    Complete pipeline for processing PowerPoint files:
    1. Extract text from slides
    2. Extract images and OCR
    3. Extract tables
    4. Normalize text
    5. Chunk for retrieval
    """
    
    # Step 1: Extract slide content
    slides = extract_pptx_text(file_path)
    metadata = extract_pptx_metadata(file_path)
    
    # Step 2: Extract tables from embedded images
    tables = extract_tables_from_pptx_slides(file_path)
    
    processed_slides = []
    
    for slide in slides:
        slide_num = slide["slide_num"]
        full_text = slide["full_text"]
        
        # Clean and normalize text
        cleaned_text = clean_text(full_text)
        
        # Chunk the text
        chunks = chunk_text(cleaned_text, chunk_size=1000, overlap=100)
        
        processed_slides.append({
            "slide_num": slide_num,
            "title": slide["title"],
            "original_text": full_text,
            "cleaned_text": cleaned_text,
            "chunks": [
                {
                    "chunk_num": i + 1,
                    "text": chunk
                }
                for i, chunk in enumerate(chunks)
            ]
        })
    
    return {
        "metadata": metadata,
        "slides": processed_slides,
        "tables": tables
    }
