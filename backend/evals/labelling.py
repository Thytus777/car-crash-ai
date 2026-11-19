"""Image preparation and case saving for the labelling tool (make label).

Kept free of Streamlit so it can be tested. Every saved image is:
EXIF-rotated, RGB, at most 1600 px on its long edge, JPEG under 1 MB, with
detected faces and number plates (plus any boxes the labeller adds) blurred.

Automatic detection uses OpenCV's bundled Haar cascades: good on frontal
faces, weak on side profiles and on non-Russian plate formats. The tool
always shows the result and lets the labeller add boxes before saving.
"""

import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps

from app.services.redaction import get_redactor
from evals.dataset import DATASET_ROOT, LOCAL_IMAGES_ROOT, MAX_BYTES, MAX_EDGE_PX
from evals.schema import CaseLabel

Box = tuple[int, int, int, int]  # x, y, width, height in pixels of the resized image

# Haar cascade XML files bundled with opencv-python(-headless) 4.x.
_CASCADE_DIR = Path(cv2.__file__).parent / "data"
_CASCADES = {
    "face": ["haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"],
    "plate": ["haarcascade_russian_plate_number.xml"],
}


@dataclass(frozen=True)
class PreparedImage:
    jpeg: bytes
    size: tuple[int, int]
    detected: dict[str, list[Box]]
    blurred: list[Box]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.jpeg).hexdigest()


def detect_sensitive_regions(img: Image.Image) -> dict[str, list[Box]]:
    """Faces and plates: the service's detectors if installed, else Haar."""
    redactor = get_redactor()
    if redactor is not None:
        plates, faces = redactor.detect(img)
        return {"face": faces, "plate": plates}
    return _haar_regions(img)


def _haar_regions(img: Image.Image) -> dict[str, list[Box]]:
    """Fallback: OpenCV's bundled Haar cascades (weak on plates)."""
    gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    found: dict[str, list[Box]] = {}
    for kind, files in _CASCADES.items():
        boxes: list[Box] = []
        for name in files:
            cascade = cv2.CascadeClassifier(str(_CASCADE_DIR / name))
            hits = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            boxes += [(int(x), int(y), int(w), int(h)) for x, y, w, h in hits]
        found[kind] = boxes
    return found


def blur_regions(img: Image.Image, boxes: list[Box], pad: float = 0.15) -> Image.Image:
    """Heavily blur each box, padded by `pad` of its size on every side."""
    out = img.copy()
    for x, y, w, h in boxes:
        dx, dy = int(w * pad), int(h * pad)
        region = (
            max(0, x - dx),
            max(0, y - dy),
            min(img.width, x + w + dx),
            min(img.height, y + h + dy),
        )
        if region[2] <= region[0] or region[3] <= region[1]:
            continue
        radius = max(8, (region[2] - region[0]) // 6)
        out.paste(out.crop(region).filter(ImageFilter.GaussianBlur(radius)), region)
    return out


def _encode_under_limit(img: Image.Image) -> bytes:
    for quality in (88, 80, 72, 64, 56):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    raise ValueError("image can't be compressed under 1 MB at 1600 px")


def prepare_image(data: bytes, extra_boxes: list[Box] | None = None) -> PreparedImage:
    """Normalise, resize, detect and blur one uploaded photo."""
    img = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
    img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.Resampling.LANCZOS)
    detected = detect_sensitive_regions(img)
    boxes = [b for found in detected.values() for b in found] + list(extra_boxes or [])
    img = blur_regions(img, boxes)
    return PreparedImage(
        jpeg=_encode_under_limit(img), size=img.size, detected=detected, blurred=boxes
    )


def save_case(
    label: CaseLabel,
    images: dict[str, bytes],
    *,
    root: Path | None = None,
    local_root: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write label.json and the prepared images where their licence allows.

    `images` maps each label image's file name to its prepared JPEG bytes;
    the label's sha256 values must match them.
    """
    root, local_root = root or DATASET_ROOT, local_root or LOCAL_IMAGES_ROOT
    directory = root / label.case_id
    if directory.exists() and not overwrite:
        raise FileExistsError(f"case {label.case_id!r} already exists")
    if set(images) != {i.file for i in label.images}:
        raise ValueError("images don't match the label's image list")
    for ref in label.images:
        if hashlib.sha256(images[ref.file]).hexdigest() != ref.sha256:
            raise ValueError(f"{ref.file}: sha256 doesn't match the label")

    (directory / "images").mkdir(parents=True, exist_ok=True)
    for ref in label.images:
        target = (
            directory / "images" / ref.file
            if ref.redistributable
            else local_root / label.case_id / ref.file
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(images[ref.file])
    body = json.loads(label.model_dump_json(exclude_defaults=False))
    (directory / "label.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return directory
