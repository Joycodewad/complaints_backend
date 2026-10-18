from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentStudent
from app.models import Category, Complaint, Status
from app.schemas.category import CategoryOut
from app.schemas.complaint import CommentCreate, ComplaintCreate, ComplaintDetail, ComplaintOut
from app.services import complaint_service as svc

router = APIRouter()


def _own(db, complaint_id: int, student) -> Complaint:
    complaint = svc.get_complaint_or_404(db, complaint_id)
    if complaint.student_id != student.id:
        raise HTTPException(404, "Plainte introuvable")  # 404 : on ne révèle pas l'existence
    return complaint


@router.get("/categories", response_model=list[CategoryOut], tags=["Categories"], summary="Catégories actives")
def list_categories(db: DB, _: CurrentStudent):
    return db.scalars(select(Category).where(Category.is_active).order_by(Category.name)).all()


@router.post("/complaints", response_model=ComplaintDetail, status_code=201, tags=["My complaints"],
             summary="Soumettre une plainte")
def create_complaint(data: ComplaintCreate, db: DB, student: CurrentStudent):
    """La référence `CMP-YYYY-0001` est générée par le serveur. Le statut initial est `SUBMITTED`."""
    return svc.create_complaint(db, student, data)


@router.get("/complaints", response_model=list[ComplaintOut], tags=["My complaints"], summary="Lister mes plaintes")
def list_my_complaints(db: DB, student: CurrentStudent,
                       status: Status | None = Query(None), skip: int = 0, limit: int = Query(50, le=200)):
    stmt = select(Complaint).where(Complaint.student_id == student.id)
    if status:
        stmt = stmt.where(Complaint.status == status)
    return db.scalars(stmt.order_by(Complaint.created_at.desc()).offset(skip).limit(limit)).all()


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetail, tags=["My complaints"],
            summary="Détail, commentaires et historique de statut")
def get_my_complaint(complaint_id: int, db: DB, student: CurrentStudent):
    return _own(db, complaint_id, student)


@router.post("/complaints/{complaint_id}/comments", response_model=ComplaintDetail, status_code=201,
             tags=["My complaints"], summary="Ajouter un message à ma plainte")
def comment_my_complaint(complaint_id: int, data: CommentCreate, db: DB, student: CurrentStudent):
    complaint = _own(db, complaint_id, student)
    return svc.add_comment(db, complaint, student, data.message, is_resolution=False)
