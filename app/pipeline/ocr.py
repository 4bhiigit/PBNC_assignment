import logging
from dataclasses import dataclass, field

import numpy as np

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class OCRWord:
    text: str
    conf: float  # 0.0 to 1.0
    bbox: list[int]  # [x, y, w, h]


@dataclass
class OCRResult:
    text: str
    mean_confidence: float  # 0.0 to 1.0
    words: list[OCRWord] = field(default_factory=list)


def run_ocr(image: np.ndarray, langs: str = "eng") -> OCRResult:
    """Runs Tesseract OCR extracting word bounding boxes and confidence scores."""
    if pytesseract is None:
        logger.warning("pytesseract is not available; OCR skipped")
        return OCRResult(text="", mean_confidence=0.0, words=[])

    try:
        data = pytesseract.image_to_data(
            image,
            lang=langs,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        logger.warning("Tesseract execution failed or binary not found: %s", exc)
        return OCRResult(text="", mean_confidence=0.0, words=[])

    n_boxes = len(data.get("text", []))
    words: list[OCRWord] = []
    lines: dict[tuple[int, int, int], list[str]] = {}

    for i in range(n_boxes):
        raw_text = data["text"][i].strip()
        conf_val = float(data["conf"][i])
        if not raw_text or conf_val < 0:
            continue

        norm_conf = max(0.0, min(1.0, conf_val / 100.0))
        bbox = [
            int(data["left"][i]),
            int(data["top"][i]),
            int(data["width"][i]),
            int(data["height"][i]),
        ]
        words.append(OCRWord(text=raw_text, conf=norm_conf, bbox=bbox))

        line_key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        if line_key not in lines:
            lines[line_key] = []
        lines[line_key].append(raw_text)

    # Reconstruct text lines
    text_lines = [" ".join(words_in_line) for words_in_line in lines.values()]
    full_text = "\n".join(text_lines)

    mean_conf = float(sum(w.conf for w in words) / len(words)) if words else 0.0

    return OCRResult(
        text=full_text,
        mean_confidence=mean_conf,
        words=words,
    )
