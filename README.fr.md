# Complaint Management API (FastAPI)

Les étudiants soumettent des plaintes, l'administrateur les classe et les assigne, le coordinateur les traite, l'administrateur les clôture.

## Lancer le projet
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # puis changer SECRET_KEY
python -m scripts.seed          # admin / coord / student  (mot de passe : Password123!)
uvicorn app.main:app --reload
pytest                          # tests
```

## Une documentation Swagger par rôle
| Rôle | Swagger | ReDoc |
|---|---|---|
| Étudiant | http://localhost:8000/api/student/docs | /api/student/redoc |
| Coordinateur | http://localhost:8000/api/coordinator/docs | /api/coordinator/redoc |
| Administrateur | http://localhost:8000/api/admin/docs | /api/admin/redoc |
| Auth (commun) | http://localhost:8000/docs | |

Chaque rôle est une sous-application FastAPI montée sur son préfixe : son OpenAPI ne contient que ses propres routes.
Bouton **Authorize** : saisir `username` / `password` (l'endpoint `/auth/login` est partagé).

## Structure
```
app/
├── main.py                 # app racine, /auth, montage des 3 sous-apps
├── core/                   # config, sécurité (JWT, bcrypt), utils
├── db/                     # Base SQLAlchemy, session
├── models/                 # User, Department, Category, Complaint, ComplaintComment, StatusHistory, Notification
├── schemas/                # Schémas Pydantic (entrées/sorties)
├── services/               # Logique métier : machine à états, assignation, notifications, référence CMP-YYYY-0001
└── api/
    ├── deps.py             # get_current_user, require_roles
    ├── auth.py             # login, me
    ├── shared/             # notifications (partagé)
    ├── student/            # routes + Swagger étudiant
    ├── coordinator/        # routes + Swagger coordinateur
    └── admin/              # complaints, users, referentials + Swagger admin
scripts/seed.py             # données de démo
tests/                      # cycle de vie complet, isolation des rôles, Swagger par rôle
```

## Règles métier
Cycle : `SUBMITTED → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED` (`RESOLVED → IN_PROGRESS` = réouverture).

| Action | Student | Coordinator | Admin |
|---|---|---|---|
| Créer une plainte | ✅ | ❌ | ❌ |
| Voir | les siennes | celles assignées | toutes |
| Assigner / priorité | ❌ | ❌ | ✅ |
| `IN_PROGRESS`, `RESOLVED` | ❌ | ✅ | ✅ |
| `CLOSED` / réouvrir | ❌ | ❌ | ✅ |
| Commentaire | ✅ | ✅ (+ résolution) | ✅ |
| Users, départements, catégories, stats | ❌ | ❌ | ✅ |

* `StatusHistory` est alimenté uniquement par le service, aucune route ne l'écrit (lecture seule).
* `User.student_id` (matricule) ≠ `Complaint.student_id` (clé étrangère vers `users.id`).
* Production : remplacer `create_all` par Alembic et utiliser PostgreSQL.

## Pagination
Toutes les listes de plaintes (`GET /api/{student|coordinator|admin}/complaints`) sont paginées côté serveur :

| Paramètre | Défaut | Règle |
|---|---|---|
| `skip` | 0 | ≥ 0 |
| `limit` | 50 | 1 à 200 |
| `q` | — | recherche référence/titre (étudiant, coordinateur, admin) |
| `status` | — | filtre par statut |

* Le nombre **total** de résultats (avant pagination) est renvoyé dans l'en-tête `X-Total-Count` (exposé en CORS).
* Ordre stable : plus récentes d'abord, `id` décroissant en départage (pas de doublon ni d'oubli entre deux pages).
* `GET /api/student/stats` et `GET /api/coordinator/stats` : nombre de plaintes par statut (compteurs exacts sans charger les listes).
