from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.db.base import Base
from app.models.enums import Status


class StatusHistory(Base):
    """Journal en lecture seule : aucune route ne permet de le modifier."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    old_status: Mapped[Status | None] = mapped_column(Enum(Status), nullable=True)
    new_status: Mapped[Status] = mapped_column(Enum(Status))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    complaint = relationship("Complaint", back_populates="history")
    changed_by = relationship("User")
