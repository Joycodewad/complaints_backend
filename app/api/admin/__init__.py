from fastapi import FastAPI

from app.api.admin import complaints, referentials, users
from app.api.shared import notifications

DESCRIPTION = """
## API Administrateur 🛠️
Réservée aux utilisateurs de rôle **ADMIN**.

**Ce que vous pouvez faire**
* Voir et filtrer **toutes** les plaintes, assigner/réassigner, définir la priorité
* Clôturer (`RESOLVED → CLOSED`) ou rouvrir (`RESOLVED → IN_PROGRESS`) une plainte
* Gérer les utilisateurs, départements et catégories
* Consulter les statistiques

**Cycle de vie** : `SUBMITTED → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED`

**Authentification** : `POST /auth/login` (bouton *Authorize*).
"""

app = FastAPI(
    title="Complaint API — Admin",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=[
        {"name": "Complaints", "description": "Gestion de toutes les plaintes"},
        {"name": "Dashboard", "description": "Statistiques"},
        {"name": "Users", "description": "Comptes étudiants, coordinateurs, administrateurs"},
        {"name": "Departments", "description": "Départements (rattachés aux coordinateurs)"},
        {"name": "Categories", "description": "Catégories de plaintes"},
        {"name": "Notifications", "description": "Mes notifications"},
    ],
)
app.include_router(complaints.router)
app.include_router(users.router)
app.include_router(referentials.departments)
app.include_router(referentials.categories)
app.include_router(notifications.router)
