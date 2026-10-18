from fastapi import Response
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Complaint, Status

TOTAL_HEADER = "X-Total-Count"


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\%").replace("_", "\_")


def search_complaints(stmt: Select, q: str | None) -> Select:
    """Recherche par référence ou titre (insensible à la casse, % et _ traités littéralement)."""
    q = (q or "").strip()
    if not q:
        return stmt
    pattern = f"%{escape_like(q)}%"
    return stmt.where(or_(Complaint.reference.ilike(pattern, escape="\\"), Complaint.title.ilike(pattern, escape="\\")))


def paginate_complaints(db: Session, stmt: Select, response: Response, skip: int, limit: int) -> list[Complaint]:
    """Applique un ordre stable (récentes d'abord, id en départage), la fenêtre skip/limit,
    et renvoie le nombre total de résultats dans l'en-tête X-Total-Count."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    response.headers[TOTAL_HEADER] = str(total)
    return db.scalars(stmt.order_by(Complaint.created_at.desc(), Complaint.id.desc()).offset(skip).limit(limit)).all()


def status_counts(db: Session, *conditions) -> dict:
    """Nombre de plaintes par statut (toujours les 5 statuts, même à 0)."""
    rows = db.execute(select(Complaint.status, func.count()).where(*conditions).group_by(Complaint.status)).all()
    by_status = {s.value: 0 for s in Status}
    for status, n in rows:
        by_status[status.value] = n
    return {"total": sum(by_status.values()), "by_status": by_status}
