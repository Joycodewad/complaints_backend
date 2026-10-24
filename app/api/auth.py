from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.user import Token, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token, summary="Obtain a token JWT")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    """Sign in with **email** and password (the form field is named `username` by the OAuth2 standard).
    Common to three roles. the token give access API for role correspondante :
    `/api/student`, `/api/coordinator` ou `/api/admin`."""
    ident = form.username.strip()
    user = db.scalar(select(User).where(func.lower(User.email) == ident.lower()))  # identifiant = email
    if user is None:
        user = db.scalar(select(User).where(User.username == ident))  # repli : ancien identifiant
    if not user or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects")
    return Token(access_token=create_access_token(user.id, user.role.value), role=user.role)


@router.get("/me", response_model=UserOut, summary="Profil of the current user")
def me(user: CurrentUser):
    return user
