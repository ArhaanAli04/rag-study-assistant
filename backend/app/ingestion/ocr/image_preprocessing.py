from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

# Below this many ink pixels the fitted rectangle says nothing about skew, so the page is left as is.
MIN_TEXT_PIXELS = 50


def estimate_skew_angle(gray: np.ndarray) -> float:
    """Angle in degrees, in (-45, 45], to pass to cv2.getRotationMatrix2D to level the text."""
    # Imported here: OpenCV costs ~1 s at import, and only the deskew step needs it.
    import cv2

    # Inverted Otsu makes the ink the foreground. Fitting the rectangle to every non-black pixel
    # instead (the old code) fits the paper, i.e. the whole page (B5).
    _, text_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    rows, cols = np.nonzero(text_mask)
    if rows.size < MIN_TEXT_PIXELS:
        return 0.0

    # minAreaRect wants (x, y) points; np.nonzero returns (row, col), which mirrors the angle.
    points = np.column_stack((cols, rows)).astype(np.float32)
    angle = cv2.minAreaRect(points)[-1]
    # OpenCV >= 4.5 reports (0, 90]: an upright page comes back as 90, which the old pre-4.5
    # branch turned into a quarter turn. Fold it onto the skew range instead.
    if angle > 45:
        angle -= 90
    return float(angle)


def preprocess_image(image_path: str) -> str:
    """
    Deskew, denoise, and enhance scanned images for OCR/table extraction.
    Returns processed image path.
    """
    import cv2

    img = Image.open(image_path)
    img = img.convert('L')

    # Noise removal
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # Contrast enhancement
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2)

    np_img = np.array(img)
    angle = estimate_skew_angle(np_img)

    (h, w) = np_img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    # Same width x height as the input: the correction is under 45 degrees, so the text stays on the page.
    rotated = cv2.warpAffine(np_img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    final_img = Image.fromarray(rotated)
    processed_path = image_path.replace('.png', '_preprocessed.png').replace('.jpg', '_preprocessed.jpg')
    final_img.save(processed_path)
    return processed_path


def preprocess_image_extra(image_path):
    """
    Enhanced preprocessing for faint or low-quality images:
    - Grayscale conversion
    - Resize (doubles resolution)
    - Strong contrast enhancement
    - Sharpening
    """
    img = Image.open(image_path)
    img = img.convert('L')
    img = img.resize((img.width*2, img.height*2))
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(3)  # Even more contrast
    img = img.filter(ImageFilter.SHARPEN)
    processed_path = image_path.replace('.png', '_extra.png').replace('.jpg', '_extra.jpg')
    img.save(processed_path)
    return processed_path
