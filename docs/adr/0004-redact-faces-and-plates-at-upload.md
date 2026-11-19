# 0004. Redact faces and number plates at upload, with pretrained ONNX detectors

- **Status:** Accepted
- **Date:** 2026-11-19
- **Issue:** #10

## Context

Crash photos routinely show number plates, and sometimes bystanders, drivers or people at the scene. Before this change, originals were stored on disk indefinitely and sent unredacted to third-party model APIs.

The eval labelling tool used OpenCV's Haar cascades. Those reliably find frontal faces, but miss side-on faces and **most non-Russian plate formats, including Australian ones**. That's acceptable as a hint for a human labeller who checks every photo; it isn't acceptable for automatic redaction of user uploads.

## Decision

Run two pretrained ONNX detectors in `process_upload()`, after resizing and **before anything is written or sent**:

| Purpose | Model | Size | Licence |
|---|---|---|---|
| Number plates | `yolo-v9-t-640-license-plates-end2end` from [open-image-models](https://github.com/ankandrew/open-image-models), run via `onnxruntime` | 7.8 MB | MIT (repository and weights release) |
| Faces | YuNet `face_detection_yunet_2023mar` from [OpenCV Zoo](https://github.com/opencv/opencv_zoo), run via `cv2.FaceDetectorYN` | 0.2 MB | Apache-2.0 |

- Detected regions are padded by 20%, pixelated, then blurred, so the original detail can't be recovered.
- Models are fetched by `scripts/fetch_models.py`, pinned by URL and sha256: at Docker build time, in CI (cached), and by `make setup` / `make models` locally. They're never committed (the repo has a 1 MB file limit) and never downloaded at runtime.
- `REDACTION_REQUIRED=true` (the Docker image default) refuses uploads and fails readiness if the models are missing, so the deployed service can never quietly store an unredacted photo.

**Thresholds favour privacy.** The plate threshold is 0.25: it's better to blur a bumper than to leak a plate. The upstream author reports precision 0.966 and recall 0.896 for this plate model. Those are their numbers, on their dataset, and haven't been verified here.

## Spot check (4 committed photos, 2026-11-19)

| Photo | Plates found | Faces found | By eye |
|---|---|---|---|
| `350z.jpg` | 0 | 0 | Correct: no readable plate in frame |
| `bmw 1 series.jpg` | 0 | 1 (≈10 px, bystander at left) | Correct face. Two other distant people (turned away or tiny) not found |
| `bmwe92_on_towtruck.jpg` | 1 (conf 0.47) | 0 | **False positive:** the car has no front plate; the box covers the damaged lower bumper |
| `holden.webp` | 1 (conf 0.55) | 0 | Plausible: plate area of a background vehicle |

That's 4 photos, so this is a sanity check, not a measurement. It shows the main cost of over-blurring: **a false plate on a damaged bumper hides damage from the model.**

## Consequences

- **Accuracy impact:** redaction can occlude damage near the plate area (front/rear bumper centre). The eval harness should compare runs with redaction on and off (`REDACTION_REQUIRED=false` and models moved away) once the labelled dataset exists, and threshold changes should be judged on that comparison.
- **Weights licence:** the plate weights are published under the repository's MIT licence. They were trained with the YOLOv9 architecture, whose reference implementation is GPL-3.0, and the licence of weights trained with GPL code is legally unsettled. That's acceptable for this portfolio project. A commercial deployment should get legal review, or train or obtain a plate detector with unambiguous terms.
- **Runtime cost:** about 8 MB more in the image, `onnxruntime` as a dependency, and tens of milliseconds of CPU per image at upload. That fits inside the upload SLO (p99 ≤ 5 s); measure it in the next load test.
- **Retention:** redacted photos are now also deleted after 24 h (`docs/DATA_RETENTION.md`).

## Alternatives considered

- **Haar cascades (the existing labelling tool):** no download, but plate recall on non-Russian formats is too poor for automatic use.
- **Provider-side redaction or vision APIs:** this would send unredacted photos to another third party, which defeats the purpose.
- **Ultralytics YOLO plate models:** strong, but AGPL-3.0.
- **Training our own detector:** the right long-term answer for licence clarity, but it needs a labelled plate dataset this project doesn't have.
