"""Regression tests for #2: upload_id must not escape the upload directory."""

from pathlib import Path

import pytest

from app.core.errors import InvalidInputError
from app.services.image_proc import load_images


@pytest.mark.parametrize("upload_id", ["../outside", "..", "a/../../outside"])
def test_load_images_rejects_ids_that_escape_upload_dir(
    isolated_upload_dir: Path, upload_id: str
) -> None:
    outside = isolated_upload_dir.parent / "outside"
    outside.mkdir(parents=True)
    (outside / "secret.jpg").write_bytes(b"not-for-the-llm")

    with pytest.raises(InvalidInputError, match="Invalid upload_id"):
        load_images(upload_id)


def test_load_images_accepts_generated_ids(isolated_upload_dir: Path) -> None:
    upload_dir = isolated_upload_dir / "0123456789ab"
    upload_dir.mkdir(parents=True)
    (upload_dir / "img.jpg").write_bytes(b"jpeg")

    assert load_images("0123456789ab") == [b"jpeg"]
