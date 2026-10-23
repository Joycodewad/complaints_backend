"""Allow complaints without a legacy attachment.

Revision ID: bf4c18a2d650
Revises: 6c0607aacefa
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bf4c18a2d650"
down_revision: Union[str, Sequence[str], None] = "6c0607aacefa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("complaints"):
        return

    columns = {column["name"]: column for column in inspector.get_columns("complaints")}
    attachment = columns.get("attachment")
    if attachment is not None and not attachment["nullable"]:
        with op.batch_alter_table("complaints") as batch_op:
            batch_op.alter_column(
                "attachment",
                existing_type=attachment["type"],
                existing_nullable=False,
                nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("complaints"):
        return

    columns = {column["name"]: column for column in inspector.get_columns("complaints")}
    attachment = columns.get("attachment")
    if attachment is not None and attachment["nullable"]:
        op.execute(sa.text("UPDATE complaints SET attachment = '' WHERE attachment IS NULL"))
        with op.batch_alter_table("complaints") as batch_op:
            batch_op.alter_column(
                "attachment",
                existing_type=attachment["type"],
                existing_nullable=True,
                nullable=False,
            )
