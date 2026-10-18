from typing import Literal

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.models.enums import Role
from app.schemas.department import DepartmentOut


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


Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class UserCreate(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)]
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: Trimmed = ""
    last_name: Trimmed = ""
    # This endpoint creates student accounts only. Elevated roles are managed
    # outside the user supplied create payload.
    # role: Literal[Role.STUDENT] = Role.STUDENT
    role: Role = Role.STUDENT
    department_id: int | None = Field(None, description="Obligatoire pour un COORDINATOR")
    student_id: Trimmed | None = Field(None, description="Matricule, obligatoire pour un STUDENT")

    @model_validator(mode="after")
    def check_role_fields(self):
        if not self.username:
            raise ValueError("username est obligatoire")
        if self.role == Role.STUDENT and not self.student_id:
            raise ValueError("student_id est obligatoire pour un étudiant")
        if self.role == Role.COORDINATOR and not self.department_id:
            raise ValueError("department_id est obligatoire pour un coordinateur")
        return self


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: Trimmed | None = None
    last_name: Trimmed | None = None
    password: str | None = Field(None, min_length=8)
    is_active: bool | None = None
    department_id: int | None = None
    student_id: Trimmed | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
