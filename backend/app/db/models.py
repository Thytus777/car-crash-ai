"""SQLAlchemy ORM models for persisting estimates and upload sessions."""

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    estimates: Mapped[list["EstimateRecord"]] = relationship(
        "EstimateRecord", back_populates="upload_session"
    )

    @property
    def quality_warnings(self) -> list[dict]:
        if self.quality_warnings_json:
            return json.loads(self.quality_warnings_json)
        return []

    @quality_warnings.setter
    def quality_warnings(self, value: list[dict]) -> None:
        self.quality_warnings_json = json.dumps(value)


class EstimateRecord(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("upload_sessions.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Vehicle
    vehicle_make: Mapped[str] = mapped_column(String(100))
    vehicle_model: Mapped[str] = mapped_column(String(100))
    vehicle_year: Mapped[int] = mapped_column(Integer)
    vehicle_vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    vehicle_confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # Totals
    parts_total: Mapped[float] = mapped_column(Float)
    labor_total: Mapped[float] = mapped_column(Float)
    grand_total: Mapped[float] = mapped_column(Float)

    # Full report stored as JSON for retrieval
    report_json: Mapped[str] = mapped_column(Text)

    upload_session: Mapped["UploadSession"] = relationship(
        "UploadSession", back_populates="estimates"
    )
