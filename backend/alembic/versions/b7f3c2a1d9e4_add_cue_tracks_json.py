"""add cue tracks json

Revision ID: b7f3c2a1d9e4
Revises: 0009b157d164
Create Date: 2026-11-16 16:10:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f3c2a1d9e4'
down_revision: str | None = '0009b157d164'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'albums',
        sa.Column('cue_tracks_json', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column('albums', 'cue_tracks_json')
