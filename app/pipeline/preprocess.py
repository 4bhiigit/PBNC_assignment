import io
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore


@dataclass
class PreprocessResult:
    """Outcome of image quality analysis and OCR-optimizing preprocessing."""

    processed_image: np.ndarray
    rotation_applied: int = 0
    deskew_angle: float = 0.0
    blur_score: float = 0.0
    effective_dpi: int = 200
    flags: list[str] = field(default_factory=list)


def calculate_blur_score(gray: np.ndarray) -> float:
    """Computes the variance of the Laplacian as a measure of image sharpness."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def estimate_effective_dpi(width: int, height: int) -> int:
    """Estimates effective DPI assuming standard A4 document dimensions (8.27 x 11.69 in)."""
    dpi_w = width / 8.27
    dpi_h = height / 11.69
    return max(1, int(round(max(dpi_w, dpi_h))))


def detect_orientation(gray: np.ndarray) -> int:
    """Detects text orientation (0, 90, 180, 270) using Tesseract OSD if available."""
    if pytesseract is None:
        return 0
    try:
        osd = pytesseract.image_to_osd(gray, output_type=pytesseract.Output.DICT)
        rotate = int(osd.get("rotate", 0))
        return rotate if rotate in (0, 90, 180, 270) else 0
    except Exception:
        return 0


def rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
    """Rotates an image by 90, 180, or 270 degrees clockwise."""
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    elif angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def compute_deskew_angle(gray: np.ndarray) -> float:
    """Calculates deskew angle in degrees (-45 to 45) using minAreaRect on binary text pixels."""
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 50:
        return 0.0

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = 90 - angle
    else:
        angle = -angle

    # Filter out insignificant micro-jitter or 90-degree flips
    if abs(angle) < 0.3 or abs(angle) > 40.0:
        return 0.0
    return float(angle)


def deskew_image(image: np.ndarray, angle: float) -> np.ndarray:
    """Applies affine rotation around center to correct skew."""
    if abs(angle) < 0.3:
        return image
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        rot_mat,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_page_image(image_bytes: bytes) -> PreprocessResult:
    """Performs full quality assessment and preprocessing on a page render for OCR."""
    # Load image from bytes
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image = np.array(pil_img)[:, :, ::-1]  # RGB to BGR

    flags: list[str] = []
    h, w = image.shape[:2]

    # 1. Effective DPI & Upscaling
    eff_dpi = estimate_effective_dpi(w, h)
    if eff_dpi < 150:
        flags.append("LOW_RESOLUTION")
        scale = 200.0 / max(eff_dpi, 50)
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        h, w = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 2. Blur assessment
    blur_score = calculate_blur_score(gray)
    if blur_score < 100.0:
        flags.append("BLURRY")

    # 3. Orientation detection & correction
    rot_angle = detect_orientation(gray)
    if rot_angle != 0:
        image = rotate_image(image, rot_angle)
        gray = rotate_image(gray, rot_angle)
        flags.append("ROTATED_CORRECTED")

    # 4. Deskew
    deskew_angle = compute_deskew_angle(gray)
    if abs(deskew_angle) >= 0.5:
        image = deskew_image(image, deskew_angle)
        gray = deskew_image(gray, deskew_angle)

    # 5. Denoise and adaptive thresholding for OCR copy
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 11
    )

    return PreprocessResult(
        processed_image=thresh,
        rotation_applied=rot_angle,
        deskew_angle=deskew_angle,
        blur_score=blur_score,
        effective_dpi=eff_dpi,
        flags=flags,
    )
