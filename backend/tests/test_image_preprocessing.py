"""Deskew in preprocess_image (B5): the estimated angle levels skewed pages and leaves upright ones alone."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.ingestion.ocr.image_preprocessing import estimate_skew_angle, preprocess_image

PAGE_SIZE = (800, 600)


def text_page() -> Image.Image:
    """A white page with ten dark bars standing in for lines of text."""
    page = Image.new("L", PAGE_SIZE, 255)
    draw = ImageDraw.Draw(page)
    for top in range(100, 500, 40):
        draw.rectangle([100, top, 700, top + 12], fill=0)
    return page


@pytest.mark.parametrize("skew", [7.0, -7.0, 15.0])
def test_estimate_skew_angle_undoes_the_skew(skew: float) -> None:
    skewed = np.array(text_page().rotate(skew, fillcolor=255))

    # PIL rotates counter-clockwise for positive angles, as cv2.getRotationMatrix2D does, so the
    # correction is the opposite angle.
    assert estimate_skew_angle(skewed) == pytest.approx(-skew, abs=1.0)


def test_estimate_skew_angle_leaves_an_upright_page_alone() -> None:
    # The pre-B5 code returned a quarter turn here: OpenCV >= 4.5 reports an axis-aligned box as 90.
    assert estimate_skew_angle(np.array(text_page())) == pytest.approx(0.0, abs=0.5)


def test_estimate_skew_angle_blank_page() -> None:
    assert estimate_skew_angle(np.full((PAGE_SIZE[1], PAGE_SIZE[0]), 255, dtype=np.uint8)) == 0.0


def test_preprocess_image_keeps_size_and_levels_text(tmp_path: Path) -> None:
    source = tmp_path / "skewed.png"
    text_page().rotate(7.0, fillcolor=255).save(source)

    processed = Image.open(preprocess_image(str(source)))

    assert processed.size == PAGE_SIZE
    assert estimate_skew_angle(np.array(processed)) == pytest.approx(0.0, abs=1.0)
