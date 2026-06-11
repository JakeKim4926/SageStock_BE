"""create stock_meta table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_meta",
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index("ix_stock_meta_market", "stock_meta", ["market"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stock_meta_market", table_name="stock_meta")
    op.drop_table("stock_meta")
