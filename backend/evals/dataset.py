"""Load and validate the labelled dataset (evals/dataset/)."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from evals.schema import CaseLabel, ImageRef, Manifest

EVALS_ROOT = Path(__file__).resolve().parents[2] / "evals"
DATASET_ROOT = EVALS_ROOT / "dataset"
LOCAL_IMAGES_ROOT = EVALS_ROOT / "local_images"  # git-ignored

# Enforced on committed images so the repo stays small (labelling tool resizes).
MAX_EDGE_PX = 1600
MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Case:
    label: CaseLabel
    directory: Path
    local_root: Path

    @property
    def case_id(self) -> str:
        return self.label.case_id

    def image_path(self, image: ImageRef) -> Path:
        if image.redistributable:
            return self.directory / "images" / image.file
        return self.local_root / self.case_id / image.file

    def available(self) -> bool:
        """True if every image is present on this machine."""
        return all(self.image_path(i).is_file() for i in self.label.images)

    def read_images(self) -> list[tuple[str, bytes]]:
        return [(i.file, self.image_path(i).read_bytes()) for i in self.label.images]


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(root: Path | None = None) -> Manifest:
    root = root or DATASET_ROOT
    return Manifest.model_validate_json((root / "manifest.json").read_text("utf-8"))


def _case_dirs(root: Path) -> Iterator[Path]:
    yield from sorted(p for p in root.iterdir() if p.is_dir())


def load_cases(root: Path | None = None, local_root: Path | None = None) -> list[Case]:
    """Parse every case; raises if any label is invalid (run validate first)."""
    root, local_root = root or DATASET_ROOT, local_root or LOCAL_IMAGES_ROOT
    return [
        Case(
            label=CaseLabel.model_validate_json((d / "label.json").read_text("utf-8")),
            directory=d,
            local_root=local_root,
        )
        for d in _case_dirs(root)
    ]


def fingerprint(root: Path | None = None) -> str:
    """Content hash of the manifest and every label (not the images)."""
    root = root or DATASET_ROOT
    digest = hashlib.sha256((root / "manifest.json").read_bytes())
    for d in _case_dirs(root):
        digest.update(d.name.encode())
        digest.update((d / "label.json").read_bytes())
    return digest.hexdigest()[:16]


def validate(
    root: Path | None = None, local_root: Path | None = None
) -> ValidationReport:
    root, local_root = root or DATASET_ROOT, local_root or LOCAL_IMAGES_ROOT
    report = ValidationReport()
    try:
        manifest = load_manifest(root)
    except (OSError, ValidationError) as exc:
        report.errors.append(f"manifest.json: {exc}")
        return report

    labels: dict[str, CaseLabel] = {}
    for directory in _case_dirs(root):
        where = directory.name
        try:
            text = (directory / "label.json").read_text("utf-8")
            label = CaseLabel.model_validate_json(text)
        except OSError:
            report.errors.append(f"{where}: missing label.json")
            continue
        except ValidationError as exc:
            report.errors.append(f"{where}: invalid label.json: {exc}")
            continue
        if label.case_id != directory.name:
            report.errors.append(f"{where}: case_id {label.case_id!r} != folder name")
        labels[label.case_id] = label
        _check_images(Case(label, directory, local_root), report)

    for case_id in manifest.smoke:
        smoke_label = labels.get(case_id)
        if smoke_label is None:
            report.errors.append(f"manifest smoke: unknown case {case_id!r}")
        elif not all(i.redistributable for i in smoke_label.images):
            report.errors.append(
                f"manifest smoke: {case_id} has non-redistributable images, "
                "which CI can't fetch"
            )
    return report


def _check_images(case: Case, report: ValidationReport) -> None:
    where = case.case_id
    committed_dir = case.directory / "images"
    committed = (
        {p.name for p in committed_dir.iterdir()} if committed_dir.is_dir() else set()
    )
    referenced = {i.file for i in case.label.images if i.redistributable}

    for stray in sorted(committed - referenced):
        report.errors.append(
            f"{where}: images/{stray} is not a redistributable image in label.json"
        )

    for image in case.label.images:
        path = case.image_path(image)
        if not path.is_file():
            if image.redistributable:
                report.errors.append(f"{where}: missing images/{image.file}")
            else:
                report.warnings.append(
                    f"{where}: {image.file} not present locally ({path}); "
                    "the case is skipped on this machine"
                )
            continue
        if sha256_file(path) != image.sha256:
            report.errors.append(f"{where}: {image.file} sha256 mismatch")
        if image.redistributable:
            if path.stat().st_size > MAX_BYTES:
                report.errors.append(f"{where}: {image.file} is over 1 MB")
            with Image.open(path) as img:
                if max(img.size) > MAX_EDGE_PX:
                    report.errors.append(
                        f"{where}: {image.file} is {img.size[0]}x{img.size[1]}; "
                        f"the long edge must be <= {MAX_EDGE_PX}px"
                    )


def summary(root: Path | None = None) -> dict[str, object]:
    """Small description for result files and the CLI."""
    root = root or DATASET_ROOT
    cases = load_cases(root)
    return {
        "version": load_manifest(root).version,
        "fingerprint": fingerprint(root),
        "cases": len(cases),
        "available_locally": sum(c.available() for c in cases),
    }


def dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)
