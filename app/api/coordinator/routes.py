from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentCoordinator
from app.models import Complaint, Status
from app.schemas.complaint import CommentCreate, ComplaintDetail, ComplaintOut, StatusUpdate
from app.services import complaint_service as svc

router = APIRouter(tags=["Assigned complaints"])


def _assigned(db, complaint_id: int, coordinator) -> Complaint:
    complaint = svc.get_complaint_or_404(db, complaint_id)
    if complaint.assigned_to_id != coordinator.id:
        raise HTTPException(404, "Plainte introuvable")
    return complaint


@router.get("/complaints", response_model=list[ComplaintOut], summary="Plaintes qui me sont assignées")
def list_assigned(db: DB, coordinator: CurrentCoordinator,
                  status: Status | None = Query(None), skip: int = 0, limit: int = Query(50, le=200)):
    stmt = select(Complaint).where(Complaint.assigned_to_id == coordinator.id)
    if status:
        stmt = stmt.where(Complaint.status == status)
    return db.scalars(stmt.order_by(Complaint.created_at.desc()).offset(skip).limit(limit)).all()


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetail, summary="Détail d'une plainte assignée")
def get_assigned(complaint_id: int, db: DB, coordinator: CurrentCoordinator):
    return _assigned(db, complaint_id, coordinator)


@router.patch("/complaints/{complaint_id}/status", response_model=ComplaintDetail,
              summary="Changer le statut (IN_PROGRESS ou RESOLVED)")
def update_status(complaint_id: int, data: StatusUpdate, db: DB, coordinator: CurrentCoordinator):
    """Transitions autorisées : `ASSIGNED → IN_PROGRESS → RESOLVED`.
    La clôture (`CLOSED`) est réservée à l'administrateur."""
    return svc.change_status(db, _assigned(db, complaint_id, coordinator), data.status, coordinator)


@router.post("/complaints/{complaint_id}/comments", response_model=ComplaintDetail, status_code=201,
             summary="Commenter ou poster la résolution")
def comment(complaint_id: int, data: CommentCreate, db: DB, coordinator: CurrentCoordinator):
    """Avec `is_resolution=true`, le commentaire est enregistré comme résolution et la plainte passe à `RESOLVED`."""
    complaint = _assigned(db, complaint_id, coordinator)
    return svc.add_comment(db, complaint, coordinator, data.message, data.is_resolution)
