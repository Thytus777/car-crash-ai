"""Store money as NUMERIC(12, 2) instead of FLOAT.

Revision ID: 002
Revises: 001
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

_MONEY_COLUMNS = ("parts_total", "labor_total", "grand_total")


def upgrade() -> None:
    for column in _MONEY_COLUMNS:
        op.alter_column(
            "estimates",
            column,
            type_=sa.Numeric(12, 2),
            existing_type=sa.Float(),
            postgresql_using=f"{column}::numeric(12, 2)",
        )


def downgrade() -> None:
    for column in _MONEY_COLUMNS:
        op.alter_column(
            "estimates",
            column,
            type_=sa.Float(),
            existing_type=sa.Numeric(12, 2),
            postgresql_using=f"{column}::double precision",
        )
