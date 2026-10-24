from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models.enums import Role
from app.schemas.department import DepartmentOut

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    first_name: str
    last_name: str
    role: Role
    student_id: str | None = None


class UserOut(UserShort):
    email: EmailStr
    is_active: bool
    department: DepartmentOut | None = None


def _lower(v: str | None) -> str | None:
    return v.strip().lower() if isinstance(v, str) else v


class UserCreate(BaseModel):
    """Création d'un compte par l'administrateur (sprint 1, story 1) : nom, email, rôle, statut du compte."""

    email: EmailStr
    password: str = Field(min_length=8)
    first_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] = ""
    role: Role = Role.STUDENT
    is_active: bool = True
    # Facultatifs : l'identifiant de connexion est l'email ; le username est déduit de l'email s'il est omis.
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)] | None = None
    department_id: int | None = Field(None, description="Département (coordinateurs)")
    student_id: Trimmed | None = Field(None, description="Matricule (étudiants)")

    _normalize_email = field_validator("email", mode="before")(_lower)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)] | None = None
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] | None = None
    password: str | None = Field(None, min_length=8)
    role: Role | None = None
    is_active: bool | None = None
    department_id: int | None = None
    student_id: Trimmed | None = None

    _normalize_email = field_validator("email", mode="before")(_lower)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
