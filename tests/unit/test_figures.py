import io
import uuid
from pathlib import Path

from PIL import Image

from app.core.storage.local import LocalStorage
from app.pipeline.extractors.schemas import ExtractedFigure
from app.pipeline.figures import crop_image_bbox, process_question_figures


def _create_test_image_bytes(w: int = 200, h: int = 200) -> bytes:
    img = Image.new("RGB", (w, h), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_crop_image_bbox_valid() -> None:
    img_bytes = _create_test_image_bytes(200, 200)
    # Crop middle rectangle [y0, x0, y1, x1] -> [0.25, 0.25, 0.75, 0.75]
    cropped = crop_image_bbox(img_bytes, [0.25, 0.25, 0.75, 0.75])
    assert cropped is not None

    with Image.open(io.BytesIO(cropped)) as c_img:
        assert c_img.size == (100, 100)


def test_crop_image_bbox_invalid() -> None:
    img_bytes = _create_test_image_bytes(100, 100)
    # ymin >= ymax or xmin >= xmax
    assert crop_image_bbox(img_bytes, [0.8, 0.8, 0.2, 0.2]) is None
    assert crop_image_bbox(b"", [0.1, 0.1, 0.5, 0.5]) is None


def test_process_question_figures_and_tables(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    img_bytes = _create_test_image_bytes(300, 300)
    q_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    figures = [ExtractedFigure(bbox_norm=[0.1, 0.1, 0.5, 0.5], caption="Figure 1: Circuit diagram")]
    table_md = "| A | B |\n|---|---|\n| 1 | 2 |"

    assets, flags = process_question_figures(
        question_id=q_id,
        owner_id=owner_id,
        page_no=1,
        figures=figures,
        table_markdown=table_md,
        page_image_bytes=img_bytes,
        storage=storage,
    )

    assert len(assets) == 2
    kinds = [a["kind"] for a in assets]
    assert "figure" in kinds
    assert "table" in kinds

    # Verify figure was written to storage
    fig_asset = next(a for a in assets if a["kind"] == "figure")
    assert storage.exists_sync(fig_asset["storage_key"])
