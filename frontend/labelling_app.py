"""Eval labelling tool (make label). Writes evals/dataset/<case_id>/.

Follow evals/LABELLING.md. Label what you see before looking at any model
output for the case.
"""

import datetime as dt
import re
import sys
from pathlib import Path
from typing import get_args

import streamlit as st
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from evals.labelling import Box, PreparedImage, prepare_image, save_case  # noqa: E402
from evals.schema import (  # noqa: E402
    CASE_ID_PATTERN,
    CaseLabel,
    SeverityLevel,
    Tag,
)

from app.models.damage import STANDARD_COMPONENTS, DamageType  # noqa: E402
from evals import dataset  # noqa: E402

REDISTRIBUTABLE_LICENCES = {"own", "CC0", "CC-BY-4.0", "CC-BY-SA-4.0"}

st.set_page_config(page_title="Label a case", page_icon="🏷️", layout="wide")
st.title("🏷️ Label an eval case")
st.caption(
    "Follow evals/LABELLING.md. Label what you see in the photos, before "
    "looking at any model output for this case."
)


def _parse_boxes(text: str) -> list[Box]:
    """'x,y,w,h; x,y,w,h' in pixels of the resized image."""
    boxes = []
    for part in filter(None, (p.strip() for p in text.split(";"))):
        x, y, w, h = (int(v) for v in part.split(","))
        boxes.append((x, y, w, h))
    return boxes


# --- Case and provenance ---------------------------------------------------
left, right = st.columns(2)
case_id = left.text_input("Case ID", placeholder="corolla-front-night-01")
labeller = right.text_input("Labeller", value=st.session_state.get("labeller", ""))
source = left.text_input("Source (URL, dataset name, or 'own photo')")
licence = right.text_input("Licence", placeholder="own, CC-BY-4.0, unknown …")
redistributable = st.checkbox(
    "May be redistributed (commit images to git)",
    value=licence in REDISTRIBUTABLE_LICENCES,
    help="Unchecked: images are kept in evals/local_images/ (git-ignored).",
)

# --- Photos ----------------------------------------------------------------
uploads = st.file_uploader(
    "Photos (1–10)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True
)
prepared: dict[str, PreparedImage] = {}
for i, upload in enumerate(uploads or []):
    name = f"{i + 1:02d}.jpg"
    boxes_text = st.text_input(
        f"Extra blur boxes for {upload.name} (x,y,w,h; …)", key=f"boxes-{i}"
    )
    try:
        image = prepare_image(upload.getvalue(), _parse_boxes(boxes_text))
    except ValueError as exc:
        st.error(f"{upload.name}: {exc}")
        continue
    prepared[name] = image
    found = ", ".join(f"{len(v)} {k}(s)" for k, v in image.detected.items())
    st.image(
        image.jpeg,
        caption=f"{name} ← {upload.name} · {image.size[0]}x{image.size[1]} · "
        f"auto-detected {found} · {len(image.blurred)} region(s) blurred",
        use_container_width=True,
    )
if prepared:
    st.warning(
        "Check every photo: automatic detection misses side-on faces and many "
        "plate formats. Add boxes above for anything still readable."
    )

# --- Ground truth ----------------------------------------------------------
st.header("Ground truth")
t1, t2 = st.columns(2)
shows_vehicle = t1.checkbox("Shows a road vehicle", value=True)
usable = t2.checkbox("Usable for judging damage", value=True)

with st.expander("Vehicle (optional)"):
    v1, v2, v3 = st.columns(3)
    make = v1.text_input("Make")
    model = v2.text_input("Model")
    year = v3.number_input(
        "Year", min_value=1950, max_value=dt.date.today().year + 1, value=None, step=1
    )

components = st.multiselect(
    "Visibly damaged components (vehicle's left/right)",
    STANDARD_COMPONENTS,
    disabled=not (shows_vehicle and usable),
)
damages = []
for component in components:
    c1, c2 = st.columns(2)
    severity = c1.selectbox(
        f"{component}: severity", get_args(SeverityLevel), key=f"sev-{component}"
    )
    damage_type = c2.selectbox(
        f"{component}: type (optional)",
        [None, *get_args(DamageType)],
        key=f"type-{component}",
    )
    damages.append(
        {"component": component, "severity": severity, "damage_type": damage_type}
    )

cost = None
if st.checkbox("I have a trustworthy reference cost", disabled=not components):
    k1, k2, k3, k4 = st.columns(4)
    cost = {
        "currency": k1.selectbox("Currency", ["USD", "AUD"]),
        "low": f"{k2.number_input('Low', min_value=0.0, step=50.0):.2f}",
        "high": f"{k3.number_input('High', min_value=0.0, step=50.0):.2f}",
        "basis": k4.selectbox(
            "Basis", ["repair_quote", "insurer_assessment", "labeller_estimate"]
        ),
    }

suggested: list[str] = []
if shows_vehicle and usable and not components:
    suggested.append("undamaged")
if not shows_vehicle:
    suggested.append("non_vehicle")
tags = st.multiselect("Tags", get_args(Tag), default=suggested)
notes = st.text_area("Notes (optional)")

# --- Save ------------------------------------------------------------------
if st.button("💾 Save case", type="primary", disabled=not prepared):
    st.session_state["labeller"] = labeller
    if not re.fullmatch(CASE_ID_PATTERN, case_id or ""):
        st.error("Case ID: lowercase letters, digits, - and _ (3–64 characters).")
        st.stop()
    try:
        label = CaseLabel.model_validate(
            {
                "case_id": case_id,
                "images": [
                    {
                        "file": name,
                        "sha256": image.sha256,
                        "source": source,
                        "licence": licence,
                        "redistributable": redistributable,
                    }
                    for name, image in prepared.items()
                ],
                "triage": {"shows_vehicle": shows_vehicle, "usable": usable},
                "vehicle": (
                    {"make": make, "model": model, "year": int(year) if year else None}
                    if make and model
                    else None
                ),
                "damages": damages,
                "cost": cost,
                "tags": tags,
                "labeller": labeller,
                "labelled_on": dt.date.today(),
                "notes": notes,
            }
        )
        directory = save_case(label, {n: i.jpeg for n, i in prepared.items()})
    except (ValidationError, ValueError, FileExistsError) as exc:
        st.error(str(exc))
        st.stop()

    report = dataset.validate()
    st.success(f"Saved {directory.relative_to(dataset.EVALS_ROOT.parent)}")
    for problem in report.errors:
        st.error(problem)
    st.info(
        "Next: bump the version in evals/dataset/manifest.json (minor for new "
        "cases), consider adding the case to `smoke`, then run make eval-validate."
    )
