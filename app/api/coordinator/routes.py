from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import DB, CurrentCoordinator
from app.models import Complaint, Status
from app.schemas.complaint import CommentCreate, ComplaintDetail, ComplaintOut, StatusUpdate
from app.schemas.stats import StatusCounts
from app.services import complaint_service as svc
from app.services.pagination import paginate_complaints, search_complaints, status_counts

router = APIRouter(tags=["Assigned complaints"])


def _assigned(db, complaint_id: int, coordinator) -> Complaint:
    complaint = svc.get_complaint_or_404(db, complaint_id)
    if complaint.assigned_to_id != coordinator.id:
        raise HTTPException(404, "Plainte introuvable")
    return complaint


@router.get("/complaints", response_model=list[ComplaintOut], summary="Plaintes qui me sont assignées")
def list_assigned(response: Response, db: DB, coordinator: CurrentCoordinator,
                  status: Status | None = Query(None), q: str | None = Query(None, description="Référence ou titre"),
                  skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """Pagination : `skip` / `limit`. Le nombre total de résultats est dans l'en-tête `X-Total-Count`."""
    stmt = select(Complaint).where(Complaint.assigned_to_id == coordinator.id)
    if status:
        stmt = stmt.where(Complaint.status == status)
    return paginate_complaints(db, search_complaints(stmt, q), response, skip, limit)


@router.get("/stats", response_model=StatusCounts, summary="Nombre de plaintes assignées par statut")
def my_stats(db: DB, coordinator: CurrentCoordinator):
    return status_counts(db, Complaint.assigned_to_id == coordinator.id)


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
