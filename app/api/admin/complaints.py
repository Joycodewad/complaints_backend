from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentAdmin
from app.models import Category, Complaint, Priority, Status
from app.schemas.complaint import AssignIn, CommentCreate, ComplaintDetail, ComplaintOut, PriorityIn, StatusUpdate
from app.schemas.stats import StatsOut
from app.services import complaint_service as svc

router = APIRouter(tags=["Complaints"])


@router.get("/complaints", response_model=list[ComplaintOut], summary="Toutes les plaintes (filtres)")
def list_all(db: DB, _: CurrentAdmin,
             status: Status | None = None, priority: Priority | None = None,
             category_id: int | None = None, assigned_to_id: int | None = None, student_id: int | None = None,
             unassigned: bool = False, q: str | None = Query(None, description="Recherche : référence ou titre"),
             skip: int = 0, limit: int = Query(50, le=200)):
    stmt = select(Complaint)
    if status:
        stmt = stmt.where(Complaint.status == status)
    if priority:
        stmt = stmt.where(Complaint.priority == priority)
    if category_id:
        stmt = stmt.where(Complaint.category_id == category_id)
    if assigned_to_id:
        stmt = stmt.where(Complaint.assigned_to_id == assigned_to_id)
    if student_id:
        stmt = stmt.where(Complaint.student_id == student_id)
    if unassigned:
        stmt = stmt.where(Complaint.assigned_to_id.is_(None))
    if q:
        stmt = stmt.where(or_(Complaint.reference.ilike(f"%{q}%"), Complaint.title.ilike(f"%{q}%")))
    return db.scalars(stmt.order_by(Complaint.created_at.desc()).offset(skip).limit(limit)).all()


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetail, summary="Détail complet")
def get_one(complaint_id: int, db: DB, _: CurrentAdmin):
    return svc.get_complaint_or_404(db, complaint_id)


@router.patch("/complaints/{complaint_id}/assign", response_model=ComplaintDetail,
              summary="Assigner / réassigner à un coordinateur")
def assign(complaint_id: int, data: AssignIn, db: DB, admin: CurrentAdmin):
    """Une plainte `SUBMITTED` passe automatiquement à `ASSIGNED`. Une priorité peut être fixée en même temps."""
    return svc.assign(db, svc.get_complaint_or_404(db, complaint_id), data.assigned_to_id, data.priority, admin)


@router.patch("/complaints/{complaint_id}/priority", response_model=ComplaintDetail, summary="Définir la priorité")
def set_priority(complaint_id: int, data: PriorityIn, db: DB, _: CurrentAdmin):
    complaint = svc.get_complaint_or_404(db, complaint_id)
    complaint.priority = data.priority
    db.commit()
    db.refresh(complaint)
    return complaint


@router.patch("/complaints/{complaint_id}/status", response_model=ComplaintDetail,
              summary="Changer le statut (clôture, réouverture…)")
def set_status(complaint_id: int, data: StatusUpdate, db: DB, admin: CurrentAdmin):
    """`RESOLVED → CLOSED` clôture la plainte ; `RESOLVED → IN_PROGRESS` la rouvre."""
    return svc.change_status(db, svc.get_complaint_or_404(db, complaint_id), data.status, admin)


@router.post("/complaints/{complaint_id}/comments", response_model=ComplaintDetail, status_code=201,
             summary="Commenter")
def comment(complaint_id: int, data: CommentCreate, db: DB, admin: CurrentAdmin):
    return svc.add_comment(db, svc.get_complaint_or_404(db, complaint_id), admin, data.message, data.is_resolution)


@router.get("/stats", response_model=StatsOut, tags=["Dashboard"], summary="Statistiques globales")
def stats(db: DB, _: CurrentAdmin):
    complaints = db.scalars(select(Complaint)).all()
    names = dict(db.execute(select(Category.id, Category.name)).all())
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    durations = []
    for c in complaints:
        by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
        by_category[names[c.category_id]] = by_category.get(names[c.category_id], 0) + 1
        if c.resolved_at:
            durations.append((c.resolved_at - c.created_at).total_seconds() / 3600)
    return StatsOut(
        total=len(complaints), by_status=by_status, by_category=by_category,
        unassigned=sum(1 for c in complaints if c.assigned_to_id is None),
        avg_resolution_hours=round(sum(durations) / len(durations), 2) if durations else None,
    )
