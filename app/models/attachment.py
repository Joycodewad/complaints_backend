from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.db.base import Base


class Attachment(Base):
    """Image ou vidéo jointe à une plainte. Le fichier est sur disque (voir `attachment_service`)."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(200))        # nom d'origine nettoyé (affichage)
    stored_name: Mapped[str] = mapped_column(String(80))      # nom réel sur disque (uuid, jamais fourni par le client)
    content_type: Mapped[str] = mapped_column(String(50))     # déterminé depuis le contenu, pas depuis le client
    size: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    complaint = relationship("Complaint", back_populates="attachments")
    uploaded_by = relationship("User")
