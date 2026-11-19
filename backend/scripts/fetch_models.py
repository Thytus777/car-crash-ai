"""Download the redaction models into backend/models/ (git-ignored).

    python scripts/fetch_models.py        # or: make models

Each file is pinned by URL and sha256; a mismatch deletes the download and
fails. The Docker build runs this, so images ship with the models and the
service never downloads anything at runtime.
"""

import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


@dataclass(frozen=True)
class ModelFile:
    name: str
    url: str
    sha256: str
    size: int
    licence: str


MODELS = (
    ModelFile(
        name="license-plate-yolo-v9-t-640.onnx",
        url="https://github.com/ankandrew/open-image-models/releases/download/"
        "assets/yolo-v9-t-640-license-plates-end2end.onnx",
        sha256="c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076",
        size=7_835_770,
        licence="MIT (ankandrew/open-image-models); YOLOv9 architecture, see ADR 0004",
    ),
    ModelFile(
        name="face-yunet-2023mar.onnx",
        url="https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        size=232_589,
        licence="Apache-2.0 (opencv/opencv_zoo)",
    ),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(model: ModelFile, directory: Path = MODELS_DIR) -> Path:
    target = directory / model.name
    if target.is_file() and _sha256(target) == model.sha256:
        return target
    directory.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    with urllib.request.urlopen(model.url, timeout=120) as response:  # noqa: S310
        partial.write_bytes(response.read())
    digest = _sha256(partial)
    if digest != model.sha256:
        partial.unlink()
        raise RuntimeError(f"{model.name}: sha256 {digest} != pinned {model.sha256}")
    partial.replace(target)
    return target


def main() -> int:
    for model in MODELS:
        path = fetch(model)
        print(f"ok  {path.name}  ({model.size:,} bytes, {model.licence})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
