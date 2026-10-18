from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    complaint_id: int | None
    message: str
    is_read: bool
    created_at: datetime
