"""Locust users: upload one photo, then request assessments back to back."""

from io import BytesIO

from locust import HttpUser, between, task
from PIL import Image


def _red_photo() -> bytes:
    # The simulated provider's triage accepts red images as "a vehicle".
    buf = BytesIO()
    Image.new("RGB", (1280, 960), color=(200, 20, 20)).save(buf, format="JPEG")
    return buf.getvalue()


PHOTO = _red_photo()


class Assessor(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        response = self.client.post(
            "/api/v1/upload",
            files=[("images", ("car.jpg", PHOTO, "image/jpeg"))],
            name="/api/v1/upload",
        )
        response.raise_for_status()
        self.upload_id = response.json()["upload_id"]

    @task
    def analyze(self) -> None:
        self.client.post(
            "/api/v1/analyze",
            json={"upload_id": self.upload_id},
            name="/api/v1/analyze",
            timeout=180,
        )
