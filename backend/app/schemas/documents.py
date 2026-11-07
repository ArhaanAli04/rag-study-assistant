from typing import Optional

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    subject: Optional[str] = None
    file_type: Optional[str] = None  # "pdf", "pptx", "docx"
    start_doc_id: Optional[int] = None
    end_doc_id: Optional[int] = None
