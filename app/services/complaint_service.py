from fastapi import HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.utils import utcnow
from app.models import (
    Category, Complaint, ComplaintComment, Priority, Role, Status, StatusHistory, User,
)
from app.schemas.complaint import ComplaintCreate
from app.services.notification_service import notify

# Machine à états : statut actuel -> statuts atteignables
ALLOWED_TRANSITIONS: dict[Status, set[Status]] = {
    Status.SUBMITTED: {Status.ASSIGNED},
    Status.ASSIGNED: {Status.IN_PROGRESS},
    Status.IN_PROGRESS: {Status.RESOLVED},
    Status.RESOLVED: {Status.CLOSED, Status.IN_PROGRESS},  # clôture ou réouverture
    Status.CLOSED: set(),
}
COORDINATOR_ALLOWED = {Status.IN_PROGRESS, Status.RESOLVED}


def get_complaint_or_404(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Plainte introuvable")
    return complaint


def generate_reference(db: Session) -> str:
    """CMP-YYYY-0001, séquentiel par année, généré côté serveur."""
    prefix = f"CMP-{utcnow().year}-"
    last = db.scalar(
        select(Complaint.reference)
        .where(Complaint.reference.like(f"{prefix}%"))
        .order_by(Complaint.reference.desc())
        .limit(1)
    )
    number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:04d}"


def _log_status(db: Session, complaint: Complaint, old: Status | None, new: Status, user: User) -> None:
    db.add(StatusHistory(complaint=complaint, old_status=old, new_status=new, changed_by_id=user.id))


def create_complaint(db: Session, student: User, data: ComplaintCreate) -> Complaint:
    if data.category_id is not None:  # facultative : l'administrateur catégorise plus tard
        category = db.get(Category, data.category_id)
        if not category or not category.is_active:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie invalide ou inactive")

    for _ in range(3):  # retry en cas de collision de référence
        complaint = Complaint(
            reference=generate_reference(db), title=data.title, description=data.description,
            category_id=data.category_id, student_id=student.id, status=Status.SUBMITTED,
        )
        db.add(complaint)
        try:
            db.flush()
            break
        except IntegrityError:
            db.rollback()
    else:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "Impossible de générer la référence")

    _log_status(db, complaint, None, Status.SUBMITTED, student)
    admins = db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active)).all()
    for admin in admins:
        notify(db, admin.id, complaint, f"Nouvelle plainte {complaint.reference} : {complaint.title}")
    db.commit()
    db.refresh(complaint)
    return complaint


def change_status(db: Session, complaint: Complaint, new: Status, actor: User, *, commit: bool = True) -> Complaint:
    if actor.role == Role.COORDINATOR and new not in COORDINATOR_ALLOWED:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Un coordinateur ne peut pas appliquer ce statut")
    if new not in ALLOWED_TRANSITIONS[complaint.status]:
        raise HTTPException(
            http.HTTP_409_CONFLICT, f"Transition interdite : {complaint.status.value} → {new.value}"
        )

    old = complaint.status
    complaint.status = new
    now = utcnow()
    if new == Status.RESOLVED:
        complaint.resolved_at = now
    elif new == Status.CLOSED:
        complaint.closed_at = now
    elif old == Status.RESOLVED and new == Status.IN_PROGRESS:  # réouverture
        complaint.resolved_at = None
    _log_status(db, complaint, old, new, actor)

    msg = f"Plainte {complaint.reference} : {old.value} → {new.value}"
    notify(db, complaint.student_id, complaint, msg)
    if complaint.assigned_to_id != actor.id:
        notify(db, complaint.assigned_to_id, complaint, msg)
    if commit:
        db.commit()
        db.refresh(complaint)
    return complaint


def assign(db: Session, complaint: Complaint, coordinator_id: int, priority: Priority | None, admin: User) -> Complaint:
    if complaint.status not in {Status.SUBMITTED, Status.ASSIGNED, Status.IN_PROGRESS}:
        raise HTTPException(http.HTTP_409_CONFLICT, "Cette plainte ne peut plus être (ré)assignée")
    coordinator = db.get(User, coordinator_id)
    if not coordinator or coordinator.role != Role.COORDINATOR or not coordinator.is_active:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "L'assigné doit être un coordinateur actif")

    complaint.assigned_to_id = coordinator.id
    if priority:
        complaint.priority = priority
    notify(db, coordinator.id, complaint, f"La plainte {complaint.reference} vous a été assignée")
    if complaint.status == Status.SUBMITTED:
        return change_status(db, complaint, Status.ASSIGNED, admin)
    db.commit()
    db.refresh(complaint)
    return complaint


def add_comment(db: Session, complaint: Complaint, author: User, message: str, is_resolution: bool) -> Complaint:
    if complaint.status == Status.CLOSED:
        raise HTTPException(http.HTTP_409_CONFLICT, "La plainte est clôturée")
    if is_resolution:
        if author.role == Role.STUDENT:
            raise HTTPException(http.HTTP_403_FORBIDDEN, "Seul le personnel peut poster une résolution")
        if complaint.status != Status.IN_PROGRESS:
            raise HTTPException(http.HTTP_409_CONFLICT, "La plainte doit être IN_PROGRESS pour être résolue")

    db.add(ComplaintComment(complaint=complaint, author_id=author.id, message=message, is_resolution=is_resolution))
    target = complaint.assigned_to_id if author.id == complaint.student_id else complaint.student_id
    notify(db, target, complaint, f"Nouveau message sur {complaint.reference}")
    if is_resolution:
        return change_status(db, complaint, Status.RESOLVED, author)
    db.commit()
    db.refresh(complaint)
    return complaint
