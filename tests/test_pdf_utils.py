
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
import fitz
print(fitz.__doc__)

from pdf_utils import extract_pdf_text, extract_pdf_metadata
from chunking import chunk_text

def test_extract_pdf_text():
    sample_pdf = "tests/samples/samples.pdf"
    pages = extract_pdf_text(sample_pdf)
    assert len(pages) > 0
    assert pages[0]["page_num"] == 1
    assert isinstance(pages[0]["text"], str)

def test_extract_pdf_metadata():
    sample_pdf = "tests/samples/samples.pdf"
    meta = extract_pdf_metadata(sample_pdf)
    assert "title" in meta and "author" in meta

def test_chunk_text():
    sample_text = "This is sentence one.\nThis is sentence two.\n" * 100
    chunks = chunk_text(sample_text, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    assert isinstance(chunks[0], str)

# Place a test PDF in tests/samples/sample.pdf for complete testing!
