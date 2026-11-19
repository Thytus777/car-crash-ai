"""Blur faces and number plates before an image is stored or sent anywhere.

Detectors (models fetched by scripts/fetch_models.py into backend/models/):
- plates: YOLOv9-t (640 px) from open-image-models, an ONNX detector trained
  for licence plates across regions;
- faces: OpenCV Zoo YuNet, frontal and moderately turned faces.

Redaction runs in process_upload(), so originals never reach disk, logs,
model providers or the eval cache. If the models are missing, uploads are
refused when REDACTION_REQUIRED is set (production) and stored unredacted
with a warning otherwise (local development).
"""

import logging
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from open_image_models import create_detector
from open_image_models.detection.core.base import DetectionResult
from PIL import Image, ImageFilter

from app.core.config import settings
from app.core.errors import RedactionUnavailableError

logger = logging.getLogger(__name__)

PLATE_MODEL = "license-plate-yolo-v9-t-640.onnx"
FACE_MODEL = "face-yunet-2023mar.onnx"

Box = tuple[int, int, int, int]  # x, y, width, height


@dataclass
class RedactionResult:
    image: Image.Image
    plates: list[Box] = field(default_factory=list)
    faces: list[Box] = field(default_factory=list)

    @property
    def regions(self) -> int:
        return len(self.plates) + len(self.faces)


class Redactor:
    def __init__(self, models_dir: Path) -> None:
        self._plates = create_detector(
            str(models_dir / PLATE_MODEL),
            backend="yolo_v9",
            class_labels=("License Plate",),
            conf_thresh=settings.redaction_plate_threshold,
        )
        self._faces = cv2.FaceDetectorYN.create(
            str(models_dir / FACE_MODEL),
            "",
            (320, 320),
            score_threshold=settings.redaction_face_threshold,
        )

    def detect(self, img: Image.Image) -> tuple[list[Box], list[Box]]:
        bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        # One image in, so one flat list of detections out.
        detections = cast(list[DetectionResult], self._plates.predict(bgr))
        plates: list[Box] = [
            (
                d.bounding_box.x1,
                d.bounding_box.y1,
                d.bounding_box.width,
                d.bounding_box.height,
            )
            for d in detections
        ]
        height, width = bgr.shape[:2]
        self._faces.setInputSize((width, height))
        _, found = self._faces.detect(bgr)
        faces = [
            (int(x), int(y), int(w), int(h))
            for x, y, w, h, *_ in (found if found is not None else [])
        ]
        return plates, faces

    def redact(self, img: Image.Image) -> RedactionResult:
        plates, faces = self.detect(img)
        return RedactionResult(blur(img, plates + faces), plates, faces)


def blur(img: Image.Image, boxes: list[Box], pad: float = 0.2) -> Image.Image:
    """Irreversibly blur each box (padded by `pad` of its size)."""
    out = img.copy()
    for x, y, w, h in boxes:
        dx, dy = int(w * pad), int(h * pad)
        left, top = max(0, x - dx), max(0, y - dy)
        right, bottom = min(img.width, x + w + dx), min(img.height, y + h + dy)
        if right <= left or bottom <= top:
            continue
        region = (left, top, right, bottom)
        # Pixelate then blur: the original detail can't be recovered.
        small = out.crop(region).resize(
            (max(1, (right - left) // 12), max(1, (bottom - top) // 12))
        )
        coarse = small.resize((right - left, bottom - top), Image.Resampling.NEAREST)
        out.paste(coarse.filter(ImageFilter.GaussianBlur(4)), region)
    return out


@cache
def get_redactor() -> Redactor | None:
    """The process-wide redactor, or None if its model files aren't present."""
    models_dir = Path(settings.redaction_models_dir)
    missing = [m for m in (PLATE_MODEL, FACE_MODEL) if not (models_dir / m).is_file()]
    if missing:
        logger.warning(
            "Redaction models missing (%s); run `make models`", ", ".join(missing)
        )
        return None
    return Redactor(models_dir)


def redact(img: Image.Image) -> RedactionResult:
    """Redact one image, or fail/skip per REDACTION_REQUIRED if unavailable."""
    redactor = get_redactor()
    if redactor is None:
        if settings.redaction_required:
            raise RedactionUnavailableError(
                "Uploads are paused: face and number-plate redaction is not "
                "available on this server."
            )
        return RedactionResult(img)
    return redactor.redact(img)
