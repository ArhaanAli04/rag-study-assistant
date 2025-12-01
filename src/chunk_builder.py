import uuid
from typing import List
from models import DocumentChunk
from pdf_utils import extract_pdf_text
from chunking import chunk_text

def build_chunks_from_pdf(file_path: str, subject_tags: str = None, document_id:int |None = None) -> List[DocumentChunk]:
    pages = extract_pdf_text(file_path)
    file_name = file_path.split("/")[-1].split("\\")[-1]

    all_chunks: List[DocumentChunk] = []
    for page in pages:
        page_num = page["page_num"]
        text = page["text"] or ""
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        for idx, chunk_text_str in enumerate(chunks):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                text=chunk_text_str,
                file_name=file_name,
                page_num=page_num,
                chunk_index=idx,
                doc_type="pdf",
                subject_tags=subject_tags,
                extra_metadata={"document_id": document_id},
            )
            all_chunks.append(chunk)
    return all_chunks

from pptx_pipeline import process_pptx
from docx_utils import extract_docx_content

def build_chunks_from_pptx(file_path: str, subject_tags: str = None, document_id:int |None = None) -> List[DocumentChunk]:
    """
    Use the existing pptx_pipeline.process_pptx to get cleaned text + chunks per slide,
    then wrap into DocumentChunk objects.
    """
    processed = process_pptx(file_path)
    file_name = file_path.split("/")[-1].split("\\")[-1]

    all_chunks: List[DocumentChunk] = []

    for slide in processed["slides"]:
        slide_num = slide["slide_num"]
        title = slide.get("title") or ""
        for chunk_data in slide["chunks"]:
            text = chunk_data["text"] or ""
            # You can prepend title for better context if you like
            full_text = (title + "\n" + text).strip() if title else text

            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                text=full_text,
                file_name=file_name,
                page_num=slide_num,           # reuse page_num for slide number
                chunk_index=chunk_data["chunk_num"],
                doc_type="pptx",
                subject_tags=subject_tags,
                extra_metadata={"slide_title": title, "document_id": document_id},
            )
            all_chunks.append(chunk)

    return all_chunks

def build_chunks_from_docx(file_path: str, subject_tags: str = None, document_id:int |None = None) -> List[DocumentChunk]:
    """
    Build chunks from DOCX paragraphs while preserving style context.
    """
    paragraphs = extract_docx_content(file_path)
    file_name = file_path.split("/")[-1].split("\\")[-1]

    all_chunks: List[DocumentChunk] = []
    current_block_lines = []
    current_style = None

    # Simple heuristic: group consecutive paragraphs with same style
    for para in paragraphs:

        style = para.get("style", "Normal")
        text = (para.get("text") or "").strip()
        if not text:
            continue

        if current_style is None:
            current_style = style

        if style == current_style:
            current_block_lines.append(text)
        else:
            # flush previous block
            block_text = "\n".join(current_block_lines)
            if block_text:
                all_chunks.extend(
                    _chunk_docx_block(block_text, file_name, current_style, subject_tags, document_id)
                )
            # start new block
            current_block_lines = [text]
            current_style = style

    # flush last block
    if current_block_lines:
        block_text = "\n".join(current_block_lines)
        all_chunks.extend(
            _chunk_docx_block(block_text, file_name, current_style, subject_tags, document_id)
        )

    return all_chunks


def _chunk_docx_block(block_text: str, file_name: str, style: str, subject_tags: str, document_id:int |None ):
    """
    Helper to chunk a block of DOCX text and wrap into DocumentChunk objects.
    """
    chunks: List[DocumentChunk] = []
    from chunking import chunk_text  # local import to avoid cycles
    import uuid

    text_chunks = chunk_text(block_text, chunk_size=1000, overlap=100)
    for idx, chunk_str in enumerate(text_chunks):
        chunk = DocumentChunk(
            id=str(uuid.uuid4()),
            text=chunk_str,
            file_name=file_name,
            page_num=None,                 # no page numbers in DOCX by default
            chunk_index=idx,
            doc_type="docx",
            subject_tags=subject_tags,
            extra_metadata={"style": style, "document_id":document_id},
        )
        chunks.append(chunk)

    return chunks
