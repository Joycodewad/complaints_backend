from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SQLEnum

from app.db.base import Base
from app.models.enums import Role


class User(Base):
    """Équivalent d'un AbstractUser Django : identité + rôle."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    first_name: Mapped[str] = mapped_column(String(150), default="")
    last_name: Mapped[str] = mapped_column(String(150), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)

    role: Mapped[Role] = mapped_column(SQLEnum(Role), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)  # coordinateurs
    student_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)  # étudiants

    department = relationship("Department")
