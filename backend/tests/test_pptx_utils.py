import os
import shutil
from pathlib import Path
from typing import Any, List

import pytest

from app.ingestion.parsers.pptx import extract_pptx_text, extract_pptx_metadata
from app.ingestion.ocr.ocr import extract_text_from_image
from app.ingestion.tables.tables import extract_tables_from_image, extract_tables_from_pptx_slides
from app.ingestion.text_preprocessing import normalize_text, clean_text
from app.ingestion.parsers.pptx_pipeline import process_pptx
from tests.conftest import Account

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

@pytest.fixture
def table_detection_calls(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    """Records img2table's table detection, where every path to slide-image tables ends (the
    callers above it swallow exceptions, so a raising fake would go unnoticed)."""
    from img2table.document import Image as Img2TableImage

    calls: List[Any] = []
    monkeypatch.setattr(Img2TableImage, "extract_tables", lambda self, *args, **kwargs: calls.append(self) or [])
    return calls


@pytest.fixture
def deck_with_a_picture(tmp_path: Path) -> Path:
    """A one-slide deck with text and a picture: sample2.pptx has no pictures, so table extraction
    would find nothing to look at there whether it ran or not."""
    from pptx import Presentation
    from pptx.util import Inches

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Parallel architectures"
    slide.placeholders[1].text = "SIMD runs one instruction on many data elements at once."
    slide.shapes.add_picture(os.path.join(SAMPLES_DIR, "sampleimg1.png"), Inches(1), Inches(4), width=Inches(3))
    path = tmp_path / "deck_with_picture.pptx"
    deck.save(str(path))
    return path


def test_table_detection_would_see_the_picture(deck_with_a_picture: Path, table_detection_calls: List[Any]) -> None:
    # The control for the two tests below: called directly, the old extraction does reach img2table.
    extract_tables_from_pptx_slides(str(deck_with_a_picture))

    assert len(table_detection_calls) == 1


def test_process_pptx_does_not_extract_slide_image_tables(
    deck_with_a_picture: Path, table_detection_calls: List[Any]
) -> None:
    # B13 (Day 16): the tables never became chunks, and extracting them took ~half an upload's
    # working time on the HPC deck. Re-enable together with indexing them.
    result = process_pptx(str(deck_with_a_picture))

    assert set(result) == {"metadata", "slides"}
    assert "SIMD" in result["slides"][0]["cleaned_text"]
    assert table_detection_calls == []


def test_a_pptx_upload_does_not_run_table_extraction(
    client: Any, account: Account, deck_with_a_picture: Path, table_detection_calls: List[Any]
) -> None:
    response = client.post(
        "/upload", headers=account.headers,
        files={"file": ("slides.pptx", deck_with_a_picture.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["chunks_indexed"] > 0
    assert table_detection_calls == []


def test_ocr_on_sample_image():
    image_path = os.path.join(SAMPLES_DIR, "sampleimg1.png")
    if os.path.exists(image_path):
        text = extract_text_from_image(image_path)
        print("OCR Text:", text)
        assert isinstance(text, str)
        # (Optional) assert len(text) > 0

def test_opencv_contrib_build_wins() -> None:
    # B3: when a non-contrib OpenCV wheel overwrites cv2/, img2table fails on this function and
    # extract_tables_from_image silently returns []. Fix: reinstall opencv-contrib-python-headless last.
    import cv2

    assert hasattr(cv2.ximgproc, "niBlackThreshold"), (
        "non-contrib cv2 installed: pip install --no-deps --force-reinstall "
        "opencv-contrib-python-headless==4.12.0.88"
    )


def test_table_extraction_on_image(tmp_path: Path) -> None:
    # A ruled table: img2table's defaults (used by extract_tables_from_image) detect only tables
    # with ruling lines, so tableimage2.jpg (no lines) yields nothing until B7 is decided.
    sample = Path(SAMPLES_DIR) / "tableimage.png"
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

