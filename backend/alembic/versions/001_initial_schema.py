"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quality_warnings_json", sa.Text, nullable=True),
    )

    op.create_table(
        "estimates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("upload_id", sa.String(12), sa.ForeignKey("upload_sessions.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle_make", sa.String(100), nullable=False),
        sa.Column("vehicle_model", sa.String(100), nullable=False),
        sa.Column("vehicle_year", sa.Integer, nullable=False),
        sa.Column("vehicle_vin", sa.String(17), nullable=True),
        sa.Column("vehicle_confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("parts_total", sa.Float, nullable=False),
        sa.Column("labor_total", sa.Float, nullable=False),
        sa.Column("grand_total", sa.Float, nullable=False),
        sa.Column("report_json", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("estimates")
    op.drop_table("upload_sessions")
