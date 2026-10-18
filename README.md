# Complaint Management API

REST API (FastAPI + SQLAlchemy) for managing student complaints. Students lodge complaints, administrators triage and assign them, coordinators work on them, and administrators close them.

> Frontend: **[heard-react](https://github.com/paul4coding/heard-react)** (React + Vite). A French version of the original documentation is in [`README.fr.md`](README.fr.md).

## Features
- **JWT authentication** with three roles: `STUDENT`, `COORDINATOR`, `ADMIN`.
- **Complaint lifecycle** enforced by a state machine: `SUBMITTED → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED` (`RESOLVED → IN_PROGRESS` reopens).
- Server-generated references (`CMP-YYYY-0001`), priorities, comments, resolutions, read-only status history.
- In-app notifications, admin statistics, users / departments / categories management.
- **Server-side pagination**, search and filters on every complaint list.
- One Swagger UI **per role**, each mounted as its own sub-application.
- SQLite for local development, PostgreSQL (e.g. Supabase) for production.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then set SECRET_KEY (and DATABASE_URL)
python -m scripts.seed                                 # demo accounts: admin / coord / student
uvicorn app.main:app --reload                          # http://localhost:8000
pytest                                                 # 66 tests, run on a temporary SQLite database
```
Demo accounts created by the seed script use the password `admin123`. **Change or delete them before deploying.**

### Using PostgreSQL (Neon, Supabase…)
Set `DATABASE_URL` in `.env`, for example:
```
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
```
For Supabase use the **Session pooler** connection string (IPv4 compatible, port 5432), URL-encode special characters in the password, and enable RLS on the tables so the public REST API cannot expose them. Then run `python -m scripts.seed`; tables are created at startup (use Alembic for real migrations).

## API documentation
| Role | Swagger | ReDoc |
|---|---|---|
| Student | `/api/student/docs` | `/api/student/redoc` |
| Coordinator | `/api/coordinator/docs` | `/api/coordinator/redoc` |
| Administrator | `/api/admin/docs` | `/api/admin/redoc` |
| Auth (shared) | `/docs` | |

Use the **Authorize** button with a `username` / `password` (`POST /auth/login` is shared by all roles).

## Business rules
| Action | Student | Coordinator | Admin |
|---|---|---|---|
| Create a complaint | ✅ | ❌ | ❌ |
| View | own | assigned to them | all |
| Assign / set priority | ❌ | ❌ | ✅ |
| `IN_PROGRESS`, `RESOLVED` | ❌ | ✅ | ✅ |
| `CLOSED` / reopen | ❌ | ❌ | ✅ |
| Comment | ✅ | ✅ (+ resolution) | ✅ |
| Users, departments, categories, stats | ❌ | ❌ | ✅ |

- Comments are rejected on closed complaints.
- Elevated roles (`COORDINATOR`, `ADMIN`) cannot be created through the API (by design); create them with the seed script or directly in the database.
- Text input is trimmed; blank titles, descriptions and messages are rejected.

## Pagination
All complaint lists (`GET /api/{student|coordinator|admin}/complaints`) are paginated on the server:

| Parameter | Default | Rule |
|---|---|---|
| `skip` | 0 | ≥ 0 |
| `limit` | 50 | 1 to 200 |
| `q` | — | search by reference or title (all roles) |
| `status` | — | filter by status |

- The total number of matches (before pagination) is returned in the `X-Total-Count` response header (exposed through CORS).
- Stable ordering: newest first, with `id` as a tie-breaker, so pages never overlap or skip items.
- `GET /api/student/stats` and `GET /api/coordinator/stats` return per-status counts without loading the lists.

## Project structure
```
app/
├── main.py                 # root app, /auth, mounts the 3 role sub-apps, CORS
├── core/                   # settings, security (JWT, bcrypt), utils
├── db/                     # SQLAlchemy base and session
├── models/                 # User, Department, Category, Complaint, ComplaintComment, StatusHistory, Notification
├── schemas/                # Pydantic schemas
├── services/               # business logic: state machine, assignment, notifications, pagination
└── api/
    ├── deps.py             # get_current_user, require_roles
    ├── auth.py             # login, me
    ├── shared/             # notifications
    ├── student/            # student routes + Swagger
    ├── coordinator/        # coordinator routes + Swagger
    └── admin/              # complaints, users, referentials + Swagger
scripts/seed.py             # demo data
tests/                      # lifecycle, role isolation, validation, pagination (66 tests)
```

## Security notes
- Never commit `.env`; keep `SECRET_KEY` and database credentials out of version control.
- Generate a strong `SECRET_KEY` for every environment.
- Rotate any secret that has been shared or committed by mistake.
