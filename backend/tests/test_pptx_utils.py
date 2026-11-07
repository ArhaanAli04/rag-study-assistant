import os
import shutil
from pathlib import Path

import pytest

from app.ingestion.parsers.pptx import extract_pptx_text, extract_pptx_metadata
from app.ingestion.ocr.ocr import extract_text_from_image
from app.ingestion.tables.tables import extract_tables_from_image, extract_tables_from_pptx_slides
from app.ingestion.text_preprocessing import normalize_text, clean_text
from app.ingestion.parsers.pptx_pipeline import process_pptx

# Relative to this file, not the CWD: the Docker test run starts in /app/backend.
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
SAMPLE_PPTX = os.path.join(SAMPLES_DIR, "sample2.pptx")

def test_extract_pptx_text():
    sample_pptx = SAMPLE_PPTX
    if os.path.exists(sample_pptx):
        slides = extract_pptx_text(sample_pptx)
        assert len(slides) > 0
        assert "slide_num" in slides[0]
        assert "full_text" in slides[0]

def test_extract_pptx_metadata():
    sample_pptx = SAMPLE_PPTX
    if os.path.exists(sample_pptx):
        meta = extract_pptx_metadata(sample_pptx)
        assert "num_slides" in meta

def test_normalize_text():
    sample_text = "This   is    a   test    with   extra    spaces"
    normalized = normalize_text(sample_text)
    assert "  " not in normalized

def test_clean_text():
    sample_text = "Page 1\n\nThis is important content.\nPage 2"
    cleaned = clean_text(sample_text)
    assert len(cleaned) > 0

def test_process_pptx_pipeline():
    sample_pptx = SAMPLE_PPTX
    if os.path.exists(sample_pptx):
        result = process_pptx(sample_pptx)
        assert "slides" in result
        assert "metadata" in result



def test_extract_tables_from_pptx_slide_images():
    if os.path.exists(SAMPLE_PPTX):
        tables = extract_tables_from_pptx_slides(SAMPLE_PPTX)
        assert isinstance(tables, list)
        # Print first found table as CSV for verification
        if tables:
            print("--- Table from PPTX as CSV ---")
            print(tables[0]["csv"])

def test_pptx_image_ocr_on_slide():
    slides = extract_pptx_text(SAMPLE_PPTX)
    # Find images in the first slide and run OCR
    from pptx import Presentation
    prs = Presentation(SAMPLE_PPTX)
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.shape_type == 13:  # Picture
                # Save image temporarily
                import tempfile
                image = shape.image
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(image.blob)
                    tmp_path = tmp.name
                text = extract_text_from_image(tmp_path)
                print(f"--- OCR extracted text from image ---\n{text}\n")
                os.remove(tmp_path)
                # Just test that we can get a non-empty string for image OCR
                assert isinstance(text, str)
                # (Optional) Uncomment to require any text for OCR images:
                # assert len(text) > 0

def test_process_pptx_pipeline_tables_images():
    # End-to-end: does pipeline return tables and process images for OCR?
    if os.path.exists(SAMPLE_PPTX):
        result = process_pptx(SAMPLE_PPTX)
        assert "tables" in result
        assert isinstance(result["tables"], list)
        for table in result["tables"]:
            print("--- Table extracted as CSV ---")
            print(table.get("csv"))
        # Check slides text
        assert "slides" in result
        for slide in result["slides"]:
            print(f"Slide {slide['slide_num']} Title: {slide['title']}")
            print(f"Cleaned Text: ")
            print(slide["cleaned_text"])


def test_ocr_on_sample_image():
    image_path = os.path.join(SAMPLES_DIR, "sampleimg1.png")
    if os.path.exists(image_path):
        text = extract_text_from_image(image_path)
        print("OCR Text:", text)
        assert isinstance(text, str)
        # (Optional) assert len(text) > 0

@pytest.mark.xfail(
    strict=True,
    reason=(
        "B3: three OpenCV wheels share the cv2 package and a non-contrib build wins, so img2table "
        "fails on cv2.ximgproc and extract_tables_from_image returns []. Remove this marker on Day 10."
    ),
)
def test_table_extraction_on_image(tmp_path: Path) -> None:
    sample = Path(SAMPLES_DIR) / "tableimage2.jpg"
    assert sample.exists(), f"missing sample image: {sample}"
    # extract_tables_from_image writes its cleaned copy next to the input, so work on a copy
    # to keep tests/samples/ untouched.
    image = tmp_path / sample.name
    shutil.copyfile(sample, image)

    tables = extract_tables_from_image(str(image))

    assert tables, "no table extracted from a sample that contains one"
    rows, columns = tables[0]["dataframe"].shape
    assert rows >= 2 and columns >= 2
    assert tables[0]["csv"].strip()

