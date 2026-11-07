from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class DocumentChunk:
    id: str                      # unique id for this chunk
    text: str                    # chunk text
    file_name: str               # original file name
    page_num: Optional[int]      # page number for PDF, None for others
    chunk_index: int             # index of chunk within that page/file
    doc_type: str                # 'pdf', 'pptx', 'docx', 'image', etc.
    subject_tags: Optional[str] = None  # comma-separated tags or None
    extra_metadata: Optional[Dict] = None  # any other keys you want
