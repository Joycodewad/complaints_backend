from sqlalchemy.orm import Session

from app.models import Complaint, Notification


def notify(db: Session, user_id: int | None, complaint: Complaint | None, message: str) -> None:
    if user_id is None:
        return
    db.add(Notification(user_id=user_id, complaint_id=complaint.id if complaint else None, message=message))
