"""Gestion des comptes (sprint 1, story 1) : réservée aux administrateurs.

Créer, consulter, modifier et désactiver des comptes étudiant, coordinateur ou administrateur.
Garde-fous : email unique (sans tenir compte de la casse), un administrateur ne peut pas désactiver
ni rétrograder son propre compte (sinon plus personne ne pourrait gérer les comptes).
"""
import re

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentAdmin
from app.core.security import hash_password
from app.models import Department, Role, User
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.pagination import TOTAL_HEADER, escape_like

router = APIRouter(prefix="/users", tags=["Users"])

_ALLOWED_USER_UPDATE_FIELDS = {"email", "first_name", "last_name", "role", "department_id", "student_id", "is_active"}


def _email_taken(db, email: str, exclude_id: int | None = None) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt) is not None


def _make_username(db, email: str) -> str:
    """Identifiant technique déduit de l'email (partie avant @), rendu unique."""
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())[:140] or "user"
    base = base.ljust(3, "0")
    candidate, n = base, 1
    while db.scalar(select(User.id).where(User.username == candidate)):
        n += 1
        candidate = f"{base}{n}"
    return candidate


@router.post("", response_model=UserOut, status_code=201, summary="Créer un utilisateur")
def create_user(data: UserCreate, db: DB, _: CurrentAdmin):
    """Rôles possibles : `STUDENT`, `COORDINATOR`, `ADMIN`. L'identifiant de connexion est l'email."""
    if data.department_id and not db.get(Department, data.department_id):
        raise HTTPException(422, "Département introuvable")
    if _email_taken(db, data.email):
        raise HTTPException(409, "Cet email est déjà utilisé")
    username = data.username or _make_username(db, data.email)
    if data.username and db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, "Ce nom d'utilisateur est déjà utilisé")
    user = User(
        username=username, email=data.email, first_name=data.first_name, last_name=data.last_name,
        hashed_password=hash_password(data.password), role=data.role, is_active=data.is_active,
        department_id=data.department_id if data.role == Role.COORDINATOR else None,
        student_id=data.student_id if data.role == Role.STUDENT else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email, nom d'utilisateur ou matricule déjà utilisé")
    return user


@router.get("", response_model=list[UserOut], summary="Lister les utilisateurs")
def list_users(response: Response, db: DB, _: CurrentAdmin, role: Role | None = None,
               is_active: bool | None = Query(None, description="Comptes actifs / désactivés"),
               q: str | None = Query(None, description="Nom ou email"),
               skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """Pagination : `skip` / `limit` ; le total est dans l'en-tête `X-Total-Count`."""
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if q and q.strip():
        pattern = f"%{escape_like(q.strip())}%"
        full_name = User.first_name + " " + User.last_name
        stmt = stmt.where(or_(full_name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")))
    response.headers[TOTAL_HEADER] = str(db.scalar(select(func.count()).select_from(stmt.subquery())))
    return db.scalars(stmt.order_by(User.id).offset(skip).limit(limit)).all()


@router.get("/{user_id}", response_model=UserOut, summary="Détail d'un utilisateur")
def get_user(user_id: int, db: DB, _: CurrentAdmin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    return user


@router.patch("/{user_id}", response_model=UserOut, summary="Modifier / désactiver un utilisateur")
def update_user(user_id: int, data: UserUpdate, db: DB, admin: CurrentAdmin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    changes = data.model_dump(exclude_unset=True)

    if user.id == admin.id and (changes.get("is_active") is False or ("role" in changes and changes["role"] != Role.ADMIN)):
        raise HTTPException(409, "Vous ne pouvez pas désactiver ni rétrograder votre propre compte")
    if changes.get("email") and _email_taken(db, changes["email"], exclude_id=user.id):
        raise HTTPException(409, "Cet email est déjà utilisé")

    if "password" in changes:
        pw = changes.pop("password")
        if pw:
            user.hashed_password = hash_password(pw)

    for field, value in changes.items():
        if field not in _ALLOWED_USER_UPDATE_FIELDS:
            raise HTTPException(400, f"Champ non autorisé: {field}")
        if value is None and field in ("email", "first_name", "role", "is_active"):
            continue  # champs obligatoires : null = pas de modification
        if field == "department_id" and value is not None and not db.get(Department, value):
            raise HTTPException(422, "Département introuvable")
        setattr(user, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email ou matricule déjà utilisé")
    return user
