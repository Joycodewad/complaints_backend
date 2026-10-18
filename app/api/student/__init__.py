from fastapi import FastAPI

from app.api.shared import notifications
from app.api.student.routes import router

DESCRIPTION = """
## STUDENT API 🎓
For user who have role **STUDENT**.

**What are you doing here ?**
* submit complaints and view their status
* consult the history of status changes (read-only)
* exchange messages with the coordinator
* read our notifications

**Authentification** : `POST /auth/login` (bouton *Authorize*).
"""

app = FastAPI(
    title="Complaint API — Student",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=[
        {"name": "My complaints", "description": "My complaints (read only mine)"},
        {"name": "Categories", "description": "Categories of complaints available to students"},
        {"name": "Notifications", "description": "My notifications"},
    ],
)
app.include_router(router)
app.include_router(notifications.router)
