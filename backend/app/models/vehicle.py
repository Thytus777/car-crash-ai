from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    make: str = Field(..., description="Manufacturer (e.g. Toyota)")
    model: str = Field(..., description="Model name (e.g. Camry)")
    year: int = Field(..., description="Model year")
    trim: str | None = Field(default=None, description="Trim level (e.g. SE, XLE)")
    body_style: str | None = Field(
        default=None,
        description="Body style (sedan, SUV, truck, coupe, hatchback, van, wagon)",
    )
    color: str | None = Field(default=None, description="Exterior color")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="AI confidence in identification (0.0–1.0)",
    )
