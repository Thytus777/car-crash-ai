"""Typed application errors.

Each subclass fixes an HTTP status and a stable problem ``slug``; the API
layer renders them as RFC 9457 problem documents (see app/api/problems.py and
docs/errors.md). Raise these from services instead of HTTPException so
business code stays HTTP-agnostic.
"""

from typing import Any, ClassVar


class AppError(Exception):
    status: ClassVar[int] = 500
    slug: ClassVar[str] = "internal-error"
    title: ClassVar[str] = "Internal server error"

    def __init__(self, detail: str, **extensions: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extensions = extensions


class InvalidInputError(AppError):
    status = 400
    slug = "invalid-input"
    title = "Invalid input"


class PayloadTooLargeError(AppError):
    status = 413
    slug = "payload-too-large"
    title = "Upload too large"


class UnsupportedMediaTypeError(AppError):
    status = 415
    slug = "unsupported-media-type"
    title = "Unsupported image format"


class NotAVehicleError(AppError):
    status = 422
    slug = "not-a-vehicle"
    title = "No vehicle found in the images"


class UnusableImagesError(AppError):
    status = 422
    slug = "unusable-images"
    title = "Images can't be assessed"


class NotFoundError(AppError):
    status = 404
    slug = "not-found"
    title = "Resource not found"


class UpstreamRateLimitedError(AppError):
    status = 429
    slug = "upstream-rate-limited"
    title = "AI provider rate limit reached"


class UpstreamError(AppError):
    status = 502
    slug = "upstream-error"
    title = "AI provider returned an unusable response"


class UpstreamUnavailableError(AppError):
    status = 503
    slug = "upstream-unavailable"
    title = "AI provider unavailable"


class UpstreamTimeoutError(AppError):
    status = 504
    slug = "upstream-timeout"
    title = "AI provider timed out"
