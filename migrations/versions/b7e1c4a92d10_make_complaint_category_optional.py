"""make complaints.category_id optional

Release 1: students no longer choose a category; the administrator categorizes
complaints later (story 6, sprint 3). Existing complaints keep their category.

Revision ID: b7e1c4a92d10
Revises: 6c0607aacefa
Create Date: 2026-10-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1c4a92d10"
down_revision: Union[str, Sequence[str], None] = "6c0607aacefa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_complaints() -> bool:
    return "complaints" in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Les tables sont créées au démarrage de l'API (create_all) ; on ne modifie que si elle existe déjà.
    if _has_complaints():
        with op.batch_alter_table("complaints") as batch:
            batch.alter_column("category_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    if _has_complaints():
        op.execute("UPDATE complaints SET category_id = (SELECT MIN(id) FROM categories) WHERE category_id IS NULL")
        with op.batch_alter_table("complaints") as batch:
            batch.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
