from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentAdmin
from app.core.security import hash_password
from app.models import Department, Role, User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


def _assert_standard_role(role: Role | None) -> None:
    if role is None or role != Role.STUDENT:
        raise HTTPException(403, "Les rôles élevés ne peuvent pas être attribués depuis cette route")


_ALLOWED_USER_UPDATE_FIELDS = {
    "username",
    "email",
    "first_name",
    "last_name",
    "role",
    "department_id",
    "student_id",
    "is_active",
}


@router.post("", response_model=UserOut, status_code=201, summary="Créer un utilisateur")
def create_user(data: UserCreate, db: DB, _: CurrentAdmin):
    _assert_standard_role(data.role)
    if data.department_id and not db.get(Department, data.department_id):
        raise HTTPException(422, "Département introuvable")
    user = User(
        username=data.username,
        email=data.email, 
        first_name=data.first_name, last_name=data.last_name,
        hashed_password = hash_password(data.password),
        role = data.role,
        # department_id=None,
        # student_id=data.student_id,
        department_id=data.department_id if data.role == Role.COORDINATOR else None,
        student_id=data.student_id if data.role == Role.STUDENT else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "username, email ou student_id déjà utilisé")
    return user


@router.get("", response_model=list[UserOut], summary="Lister les utilisateurs")
def list_users(db: DB, _: CurrentAdmin, role: Role | None = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    return db.scalars(stmt.order_by(User.id).offset(skip).limit(limit)).all()


@router.get("/{user_id}", response_model=UserOut, summary="Détail d'un utilisateur")
def get_user(user_id: int, db: DB, _: CurrentAdmin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    return user


@router.patch("/{user_id}", response_model=UserOut, summary="Modifier / désactiver un utilisateur")
def update_user(user_id: int, data: UserUpdate, db: DB, _: CurrentAdmin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    changes = data.model_dump(exclude_unset=True)
    if "password" in changes:
        user.hashed_password = hash_password(changes.pop("password"))

    for field, value in changes.items():
        # Disallow private/dunder attributes and enforce whitelist
        if field.startswith("_") or field not in _ALLOWED_USER_UPDATE_FIELDS:
            raise HTTPException(400, f"Champ non autorisé: {field}")
        if not hasattr(User, field):
            raise HTTPException(400, f"Champ inconnu pour User: {field}")
        # Restrict role changes to standard role
        if field == "role":
            _assert_standard_role(value)
        if field == "department_id" and value is not None and not db.get(Department, value):
            raise HTTPException(422, "Département introuvable")

        setattr(user, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "email ou student_id déjà utilisé")
    return user
