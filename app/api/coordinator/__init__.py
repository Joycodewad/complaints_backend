from fastapi import FastAPI

from app.api.coordinator.routes import router
from app.api.shared import notifications

DESCRIPTION = """
## Coordinator API 🧑‍💼
For users who have role **COORDINATOR**.

**What you are doing here ?**
* read only complaints **assigned to you**
* pass the complaint to `IN_PROGRESS`, then to `RESOLVED`
* reply to the student and post the resolution (`is_resolution`)
* Read your notifications

**Authentification** : `POST /auth/login` (bouton *Authorize*).
"""

app = FastAPI(
    title="Complaint API — Coordinator",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=[
        {"name": "Assigned complaints", "description": "Complaints assigned to the coordinator (read only)"},
        {"name": "Notifications", "description": "My notifications"},
    ],
)
app.include_router(router)
app.include_router(notifications.router)
