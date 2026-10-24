from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select

from app.api.deps import DB, CurrentStudent
from app.models import Category, Complaint, Status
from app.schemas.category import CategoryOut
from app.schemas.complaint import CommentCreate, ComplaintCreate, ComplaintDetail, ComplaintOut
from app.schemas.stats import StatusCounts
from app.services import attachment_service as att
from app.services import complaint_service as svc
from app.services.pagination import paginate_complaints, search_complaints, status_counts

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
def list_my_complaints(response: Response, db: DB, student: CurrentStudent,
                       status: Status | None = Query(None), q: str | None = Query(None, description="Référence ou titre"),
                       skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """Pagination : `skip` / `limit`. Le nombre total de résultats est dans l'en-tête `X-Total-Count`."""
    stmt = select(Complaint).where(Complaint.student_id == student.id)
    if status:
        stmt = stmt.where(Complaint.status == status)
    return paginate_complaints(db, search_complaints(stmt, q), response, skip, limit)


@router.get("/stats", response_model=StatusCounts, tags=["My complaints"], summary="Nombre de mes plaintes par statut")
def my_stats(db: DB, student: CurrentStudent):
    return status_counts(db, Complaint.student_id == student.id)


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetail, tags=["My complaints"],
            summary="Détail, commentaires et historique de statut")
def get_my_complaint(complaint_id: int, db: DB, student: CurrentStudent):
    return _own(db, complaint_id, student)


@router.post("/complaints/{complaint_id}/comments", response_model=ComplaintDetail, status_code=201,
             tags=["My complaints"], summary="Ajouter un message à ma plainte")
def comment_my_complaint(complaint_id: int, data: CommentCreate, db: DB, student: CurrentStudent):
    complaint = _own(db, complaint_id, student)
    return svc.add_comment(db, complaint, student, data.message, is_resolution=False)


@router.post("/complaints/{complaint_id}/attachments", response_model=ComplaintDetail, status_code=201,
             tags=["My complaints"], summary="Joindre une image")
def upload_attachments(complaint_id: int, db: DB, student: CurrentStudent,
                       files: list[UploadFile] = File(..., description="Image (png, jpeg, gif, webp)")):
    """Sprint 1 : une image facultative par plainte, 10 Mo maximum. Le type est vérifié sur le contenu du fichier.
    Tout ou rien : si un fichier est refusé, aucun du lot n'est enregistré."""
    return att.save_uploads(db, _own(db, complaint_id, student), student, files)


@router.get("/complaints/{complaint_id}/attachments/{attachment_id}", tags=["My complaints"],
            summary="Télécharger une pièce jointe")
def get_attachment(complaint_id: int, attachment_id: int, db: DB, student: CurrentStudent):
    complaint = _own(db, complaint_id, student)
    return att.download(att.get_attachment_or_404(complaint, attachment_id))


@router.delete("/complaints/{complaint_id}/attachments/{attachment_id}", response_model=ComplaintDetail,
               tags=["My complaints"], summary="Supprimer une de mes pièces jointes")
def delete_attachment(complaint_id: int, attachment_id: int, db: DB, student: CurrentStudent):
    complaint = _own(db, complaint_id, student)
    return att.delete(db, complaint, att.get_attachment_or_404(complaint, attachment_id), student)
