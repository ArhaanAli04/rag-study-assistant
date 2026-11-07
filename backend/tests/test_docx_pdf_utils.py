"""Table, OCR and DOCX parsers on real sample files.

Each sample is copied into tmp_path first: the image preprocessors write their output next to the
input, and tests/samples/ is read-only in the container. Expected values were read from the
samples with the parsers themselves on Day 8 (host and container agree).
"""
import re
import shutil
from pathlib import Path

import pytest

from app.ingestion.ocr.image_preprocessing import preprocess_image_extra
from app.ingestion.ocr.ocr import ocr_from_image
from app.ingestion.parsers.docx import extract_docx_content
from app.ingestion.parsers.unified import DocumentParser
from app.ingestion.tables.pdf_tables import extract_tables_camelot, extract_tables_pdfplumber

SAMPLES_DIR = Path(__file__).parent / "samples"
TABLE_HEADER = ["Standout Feature", "Your Project", "NotebookLM"]
DOCX_OPENING = 'Prompt: "Generate a detailed system architecture diagram'
# Handwriting OCR is noisy and varies between Tesseract builds; both read 20+ such words today.
MIN_OCR_WORDS = 10


def sample_copy(tmp_path: Path, name: str) -> Path:
    sample = SAMPLES_DIR / name
    assert sample.exists(), f"missing sample: {sample}"
    copy = tmp_path / name
    shutil.copyfile(sample, copy)
    return copy


def ocr_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]{3,}", text)


def test_pdf_table_extraction_camelot(tmp_path: Path) -> None:
    tables = extract_tables_camelot(str(sample_copy(tmp_path, "table_test.pdf")))

    assert tables, "camelot found no table in a PDF that has one"
    assert tables[0].iloc[0].tolist() == TABLE_HEADER


def test_pdf_table_extraction_pdfplumber(tmp_path: Path) -> None:
    tables = extract_tables_pdfplumber(str(sample_copy(tmp_path, "table_test.pdf")))

    assert tables, "pdfplumber found no table in a PDF that has one"
    assert list(tables[0].columns) == TABLE_HEADER


def test_image_ocr_preprocess(tmp_path: Path) -> None:
    processed = preprocess_image_extra(str(sample_copy(tmp_path, "scan_handwritten.png")))

    text = ocr_from_image(processed)

    assert len(ocr_words(text)) >= MIN_OCR_WORDS, f"OCR read almost nothing: {text!r}"


def test_docx_extraction(tmp_path: Path) -> None:
    content = extract_docx_content(str(sample_copy(tmp_path, "test_style.docx")))

    assert content, "no paragraphs extracted"
    assert content[0]["style"] == "normal"
    assert content[0]["text"].startswith(DOCX_OPENING)


def test_unified_parser_pdf(tmp_path: Path) -> None:
    result = DocumentParser(str(sample_copy(tmp_path, "table_test.pdf"))).parse()

    assert result["type"] == "pdf"
    assert result["text"][0]["page_num"] == 1
    assert "Standout Feature" in result["text"][0]["text"]
    assert result["tables"], "no table extracted"
    assert result["tables"][0].iloc[0].tolist() == TABLE_HEADER


@pytest.mark.xfail(
    strict=True,
    reason=(
        "B5: preprocess_image's deskew counts the white background as text (97.5% of pixels), "
        "OpenCV 4.5+ reports that rectangle's angle as 90, and the page is rotated 90 degrees and "
        "cropped, so Tesseract reads nothing. Remove this marker on Day 10."
    ),
)
def test_unified_parser_image(tmp_path: Path) -> None:
    result = DocumentParser(str(sample_copy(tmp_path, "scan_handwritten.png"))).parse()

    assert result["type"] == "image"
    assert len(ocr_words(result["text"])) >= MIN_OCR_WORDS, f"OCR read almost nothing: {result['text']!r}"


def test_unified_parser_docx(tmp_path: Path) -> None:
    docx = sample_copy(tmp_path, "test_style.docx")

    result = DocumentParser(str(docx)).parse()

    assert result["type"] == "docx"
    assert result["content"] == extract_docx_content(str(docx))
    assert result["content"][0]["text"].startswith(DOCX_OPENING)
