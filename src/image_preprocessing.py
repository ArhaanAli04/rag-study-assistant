from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np

def preprocess_image(image_path):
    """
    Deskew, denoise, and enhance scanned images for OCR/table extraction.
    Returns processed image path.
    """
    img = Image.open(image_path)
    img = img.convert('L')

    # Noise removal
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # Contrast enhancement
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2)

    # Deskew using OpenCV
    np_img = np.array(img)
    coords = np.column_stack(np.where(np_img > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = np_img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
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
