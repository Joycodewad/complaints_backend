from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Role, User

# Un seul endpoint de login pour toute l'API : le bouton "Authorize" de chaque Swagger l'utilise.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DB = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DB) -> User:
    credentials_error = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Token invalide ou expiré", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        user_id = int(decode_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_error
    return user


def require_roles(*roles: Role):
    def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé : " + ", ".join(r.value for r in roles))
        return user
    return checker


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentStudent = Annotated[User, Depends(require_roles(Role.STUDENT))]
CurrentCoordinator = Annotated[User, Depends(require_roles(Role.COORDINATOR))]
CurrentAdmin = Annotated[User, Depends(require_roles(Role.ADMIN))]
