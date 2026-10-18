from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import Notification
from app.schemas.notification import NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut], summary="Mes notifications")
def list_notifications(db: DB, user: CurrentUser, unread_only: bool = False, limit: int = Query(50, ge=1, le=200)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)).all()


@router.patch("/{notification_id}/read", response_model=NotificationOut, summary="Marquer comme lue")
def mark_read(notification_id: int, db: DB, user: CurrentUser):
    notif = db.get(Notification, notification_id)
    if not notif or notif.user_id != user.id:
        raise HTTPException(404, "Notification introuvable")
    notif.is_read = True
    db.commit()
    return notif
