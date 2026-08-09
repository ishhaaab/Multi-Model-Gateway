"""add trainings table

Revision ID: d4a8b2c6f9e7
Revises: b8e4f1a2c9d3
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4a8b2c6f9e7'
down_revision: Union[str, Sequence[str], None] = 'b8e4f1a2c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trainings",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("user_id", postgresql.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_model", sa.String(length=32), nullable=False),
        sa.Column("dataset_dir", sa.String(length=512), nullable=True),
        sa.Column("artifact_filename", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sample_image", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trainings_user_id", "trainings", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_trainings_user_id", table_name="trainings")
    op.drop_table("trainings")
