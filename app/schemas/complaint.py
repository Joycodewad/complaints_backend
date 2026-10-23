from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import Priority, Status
from app.schemas.attachment import AttachmentOut
from app.schemas.category import CategoryOut
from app.schemas.user import UserShort


class ComplaintCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=5, max_length=200, examples=["Note erronée en Algorithmique"])
    description: str = Field(min_length=10, examples=["Ma note de l'examen final n'a pas été mise à jour..."])
    category_id: int


class CommentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1)
    is_resolution: bool = Field(False, description="Réservé aux coordinateurs/admins : marque la plainte comme résolue")


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author: UserShort
    message: str
    is_resolution: bool
    created_at: datetime


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    old_status: Status | None
    new_status: Status
    changed_by: UserShort
    changed_at: datetime


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reference: str
    title: str
    description: str
    category: CategoryOut
    student: UserShort
    assigned_to: UserShort | None
    status: Status
    priority: Priority | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class ComplaintDetail(ComplaintOut):
    comments: list[CommentOut] = []
    history: list[StatusHistoryOut] = []
    attachments: list[AttachmentOut] = []


class AssignIn(BaseModel):
    assigned_to_id: int = Field(description="ID d'un utilisateur COORDINATOR actif")
    priority: Priority | None = None


class PriorityIn(BaseModel):
    priority: Priority


class StatusUpdate(BaseModel):
    status: Status
