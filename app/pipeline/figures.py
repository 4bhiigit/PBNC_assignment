import io
import logging
import uuid
from typing import Any

from PIL import Image

from app.core.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def crop_image_bbox(
    image_bytes: bytes,
    bbox_norm: list[float],
) -> bytes | None:
    """Crops a bounding box [ymin, xmin, ymax, xmax] (normalized 0.0 - 1.0) from PNG bytes."""
    if not image_bytes or len(bbox_norm) < 4:
        return None

    try:
        ymin, xmin, ymax, xmax = bbox_norm[:4]
        if ymin >= ymax or xmin >= xmax or ymax <= 0.0 or xmax <= 0.0 or ymin >= 1.0 or xmin >= 1.0:
            return None

        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size

            left = max(0, min(w - 1, int(xmin * w)))
            top = max(0, min(h - 1, int(ymin * h)))
            right = max(left + 1, min(w, int(xmax * w)))
            bottom = max(top + 1, min(h, int(ymax * h)))

            if right <= left or bottom <= top:
                return None

            cropped = img.crop((left, top, right, bottom))
            out_buf = io.BytesIO()
            cropped.save(out_buf, format="PNG")
            return out_buf.getvalue()
    except Exception as exc:
        logger.warning("Failed to crop bounding box %s: %s", bbox_norm, exc)
        return None


def process_question_figures(
    question_id: uuid.UUID,
    owner_id: uuid.UUID,
    page_no: int,
    figures: list[Any],
    table_markdown: str | None,
    page_image_bytes: bytes | None,
    storage: StorageBackend,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Crops figure regions, uploads them to storage, and prepares QuestionAsset records."""
    assets: list[dict[str, Any]] = []
    flags: list[str] = []

    for fig in figures:
        bbox = getattr(fig, "bbox_norm", None) or (
            fig.get("bbox_norm") if isinstance(fig, dict) else None
        )
        caption = getattr(fig, "caption", None) or (
            fig.get("caption") if isinstance(fig, dict) else None
        )

        if not bbox or len(bbox) < 4:
            continue

        asset_id = uuid.uuid4()
        storage_key = f"{owner_id}/assets/{asset_id}.png"

        cropped_bytes = None
        if page_image_bytes:
            cropped_bytes = crop_image_bbox(page_image_bytes, bbox)

        if cropped_bytes:
            storage.save_sync(storage_key, cropped_bytes)
            # If coordinates span > 95% of page or < 2% of page, flag as unverified
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area > 0.95 or area < 0.02:
                if "FIGURE_UNVERIFIED" not in flags:
                    flags.append("FIGURE_UNVERIFIED")

            assets.append(
                {
                    "id": asset_id,
                    "question_id": question_id,
                    "kind": "figure",
                    "page_no": page_no,
                    "bbox": bbox,
                    "storage_key": storage_key,
                    "caption": caption,
                    "table_markdown": None,
                }
            )
        else:
            if "FIGURE_UNVERIFIED" not in flags:
                flags.append("FIGURE_UNVERIFIED")

    if table_markdown:
        asset_id = uuid.uuid4()
        txt_key = f"{owner_id}/assets/{asset_id}.txt"
        storage.save_sync(txt_key, table_markdown.encode("utf-8"))
        assets.append(
            {
                "id": asset_id,
                "question_id": question_id,
                "kind": "table",
                "page_no": page_no,
                "bbox": None,
                "storage_key": txt_key,
                "caption": "Table",
                "table_markdown": table_markdown,
            }
        )

    return assets, flags
