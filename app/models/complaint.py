from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.db.base import Base
from app.models.enums import Priority, Status


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # CMP-YYYY-0001
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # FK -> users.id
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.SUBMITTED, index=True)
    priority: Mapped[Priority | None] = mapped_column(Enum(Priority), nullable=True)
    attachment: Mapped[str | None] = mapped_column(String(500), nullable=True)  # fichiers à ajouter
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    category = relationship("Category")
    student = relationship("User", foreign_keys=[student_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    comments = relationship(
        "ComplaintComment", back_populates="complaint",
        order_by="ComplaintComment.created_at", cascade="all, delete-orphan",
    )
    history = relationship(
        "StatusHistory", back_populates="complaint",
        order_by="StatusHistory.changed_at", cascade="all, delete-orphan",
    )
