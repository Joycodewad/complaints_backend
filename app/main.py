from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (enregistre les tables)
from app.api import auth
from app.api.admin import app as admin_app
from app.api.coordinator import app as coordinator_app
from app.api.student import app as student_app
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # en production : utiliser Alembic
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "API form complaints. **the documentation Swagger for role** :\n\n"
        "* 🎓 Student : [/api/student/docs](/api/student/docs)\n"
        "* 🧑‍💼 Coordinator : [/api/coordinator/docs](/api/coordinator/docs)\n"
        "* 🛠️ Administrator : [/api/admin/docs](/api/admin/docs)\n\n"
        "Authentification (`/auth/login`) the same of all roles."
    ),
    openapi_tags=[{"name": "Authentication", "description": "Login JWT and profil"}],
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Total-Count"])

app.include_router(auth.router)
app.mount("/api/student", student_app)
app.mount("/api/coordinator", coordinator_app)
app.mount("/api/admin", admin_app)


@app.get("/", tags=["Root"], summary="Liens vers les documentations")
def root():
    return {
        "student_docs": "/api/student/docs",
        "coordinator_docs": "/api/coordinator/docs",
        "admin_docs": "/api/admin/docs",
        "auth_docs": "/docs",
    }
