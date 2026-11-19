"""Pre-flight check that the upload shows a vehicle that can be assessed."""

from app.core.errors import NotFoundError
from app.core.llm import generate
from app.models.llm_outputs import ImageTriage
from app.prompts import render
from app.services.image_proc import load_images


async def triage_images(upload_id: str) -> ImageTriage:
    """One low-detail look at all images; raises typed LLM errors on failure."""
    images = load_images(upload_id)
    if not images:
        raise NotFoundError(f"Upload {upload_id} has no images")
    result = await generate(
        ImageTriage,
        render("image_triage"),
        images,
        task="image_triage",
        max_output_tokens=150,
        temperature=0.0,
        image_detail="low",
    )
    return result.output
