#complete PPTX processing pipeline
from typing import Any, Dict

from app.ingestion.parsers.pptx import extract_pptx_text, extract_pptx_metadata
from app.ingestion.text_preprocessing import clean_text
from app.ingestion.chunking import chunk_text


def process_pptx(file_path: str) -> Dict[str, Any]:
    """Slide text and metadata, cleaned and chunked per slide: {"metadata", "slides"}.

    Tables in slide images are not extracted (B13, Day 16). extract_tables_from_pptx_slides
    (ingestion/tables/tables.py) used to run here, but its output never became chunks, so nothing
    was searchable from it. Measured on HPC Lecture.pptx (11 pictures, 0 real tables): 11.4 s of a
    143.3 s upload, 49% of the upload's working time once the free tier's embedding waits are left
    out. Re-enable it when tables are turned into chunks, and measure that with E4.
    """
    slides = extract_pptx_text(file_path)
    metadata = extract_pptx_metadata(file_path)

    processed_slides = []
    for slide in slides:
        full_text = slide["full_text"]
        cleaned_text = clean_text(full_text)
        chunks = chunk_text(cleaned_text, chunk_size=1000, overlap=100)
        processed_slides.append({
            "slide_num": slide["slide_num"],
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
    }
