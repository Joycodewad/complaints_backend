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
pytest                                                 # 139 tests, run on a temporary SQLite database
```
Sign in with the **email**: demo accounts created by the seed script use the password `admin123` (`admin@univ.edu`, `coord@univ.edu`, `student@univ.edu`). **Change or delete them before deploying.**

### Demo data to try the whole workflow
```bash
python -m scripts.seed_demo            # load fictitious data (safe to run twice)
python -m scripts.seed_demo --reset    # remove only the demo data
python -m scripts.seed_demo --reload   # reset, then load again
python -m scripts.seed_demo --with-categories   # same data, already categorized (Sprint 3 preview)
```
Adds 7 departments, 6 categories, 8 students, 4 coordinators, 1 admin and **37 complaints** spread over the whole lifecycle, with messages, status history and notifications:

| Status | Complaints | What to test |
|---|---|---|
| `SUBMITTED` | 12 | Admin queue: assign to a coordinator, set a priority (enough to paginate) |
| `ASSIGNED` | 8 | Coordinator: start work (`IN_PROGRESS`) |
| `IN_PROGRESS` | 6 | Coordinator: post a resolution; one was reopened after a first fix |
| `RESOLVED` | 5 | Admin: verify and close, or reopen |
| `CLOSED` | 6 | Read-only history |

Accounts added (password `Password123!`, sign in with `<username>@univ.edu`, e.g. `jordan.lee@univ.edu`): students `amara.okafor`, `kabelo.mthembu`, `lerato.dube`, `thabo.nkosi`, `zoe.martin`, `noah.dlamini`, `lina.haddad`, `omar.benali`; coordinators `priya.naidoo` (Engineering), `erik.lindqvist` (Hostel and facilities), `grace.okafor` (Library), `daniel.tan` (Finance office); admin `jordan.lee`. The accounts from `scripts.seed` (`admin`, `coord`, `student`, password `admin123`) keep working.

Demo complaints are tagged (`attachment = "demo-seed"`), so `--reset` never touches real data. All data is fictitious and the passwords are public: **remove it before going to production**.

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
- **Categories are optional (Release 1).** A student submits a title, a description and optional files; `category_id` can be omitted and the complaint shows as *uncategorized*. Categorizing is an administrator action planned for Sprint 3 (story 6). If a `category_id` is sent it is still validated. Existing databases need `ALTER TABLE complaints ALTER COLUMN category_id DROP NOT NULL` (also provided as Alembic migration `b7e1c4a92d10`).
- Text input is trimmed; blank titles, descriptions and messages are rejected.

## Attachment (one optional image)
Release plan, Sprint 1 (story 3): a complaint can have **one optional image**. Everyone who can see the complaint can view it.

| Endpoint | Who | Description |
|---|---|---|
| `POST /api/student/complaints/{id}/attachments` | owner | multipart upload, field `files` (one image); all-or-nothing |
| `GET /api/{student,coordinator,admin}/complaints/{id}/attachments/{aid}` | same rules as the complaint | returns the image (needs the `Authorization` header) |
| `DELETE /api/student/complaints/{id}/attachments/{aid}` | uploader | only while the complaint is not closed |

- `GET /complaints/{id}` returns the attachment list (`id`, `filename`, `content_type`, `size`).
- Allowed: PNG, JPEG, GIF, WebP, **10 MB** maximum. The type is detected from the **file content** (not the client header); SVG, videos and anything else are rejected (`415`). Too large: `413`. Already one image or complaint closed: `409`.
- Files are stored on disk under `UPLOAD_DIR` (default `uploads/`, git-ignored) with a random UUID name; the original name is only a sanitized label. `app/services/attachment_service.py` is the single place to change to use Supabase Storage / S3.
- Configurable: `UPLOAD_DIR`, `MAX_UPLOAD_MB` (default 10), `MAX_FILES_PER_COMPLAINT` (default 1).
- The `attachments` table is created automatically at startup.

## Accounts and sign-in (Sprint 1, stories 1 and 2)
- **Sign in with email + password**: `POST /auth/login` (form fields `username` = the email, `password`; the field name comes from the OAuth2 standard). The email is case-insensitive; the old username is still accepted as a fallback.
- **User management** (administrators only), `/api/admin/users`:
  - `POST` create an account: full name (`first_name` + `last_name`), `email`, `password` (8+ characters), `role` (`STUDENT`, `COORDINATOR`, `ADMIN`) and `is_active`. The `username` is optional (derived from the email); matricule and department are optional.
  - `GET` list with `role`, `is_active`, `q` (name or email), pagination and `X-Total-Count`; `GET /{id}`.
  - `PATCH /{id}` edit name, email, role, status (deactivate / reactivate) and reset the password.
- Emails are stored in lowercase and must be unique (case-insensitive: `409`).
- An administrator cannot deactivate or demote **their own** account (`409`), so the system can never be left without an administrator.
- A deactivated account can no longer sign in and its existing session stops working immediately.

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
scripts/seed_demo.py        # fictitious data for the whole workflow
tests/                      # lifecycle, role isolation, validation, pagination, demo seed (139 tests)
```

## Security notes
- Never commit `.env`; keep `SECRET_KEY` and database credentials out of version control.
- Generate a strong `SECRET_KEY` for every environment.
- Rotate any secret that has been shared or committed by mistake.
