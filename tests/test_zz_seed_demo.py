"""Le seeder de démo doit produire des données cohérentes avec la machine à états de l'API."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Complaint, ComplaintComment, Notification, Status, StatusHistory, User
from app.services.complaint_service import ALLOWED_TRANSITIONS
from scripts import seed_demo
from tests.conftest import auth


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _demo(db):
    return db.scalars(select(Complaint).where(Complaint.attachment == seed_demo.MARKER).order_by(Complaint.id)).all()


def test_load_is_consistent_and_idempotent(client):
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Complaint))
        seed_demo.load(db)
        seed_demo.load(db)  # second appel : aucun doublon
        demo = _demo(db)
        assert len(demo) == len(seed_demo.C)
        assert db.scalar(select(func.count()).select_from(Complaint)) == before + len(seed_demo.C)

        refs = [c.reference for c in db.scalars(select(Complaint)).all()]
        assert len(refs) == len(set(refs))  # références uniques

        # toutes les étapes du cycle de vie sont représentées, y compris des plaintes non affectées
        assert {c.status for c in demo} == set(Status)
        assert any(c.assigned_to_id is None for c in demo)
        assert sum(1 for c in demo if c.status == Status.SUBMITTED) >= 10   # file de l'admin assez longue pour paginer

        now = _now()
        for c in demo:
            hist = db.scalars(select(StatusHistory).where(StatusHistory.complaint_id == c.id)
                              .order_by(StatusHistory.changed_at, StatusHistory.id)).all()
            assert hist[0].old_status is None and hist[0].new_status == Status.SUBMITTED
            for prev, cur in zip(hist, hist[1:]):
                assert cur.old_status == prev.new_status, c.reference               # chaîne continue
                assert cur.new_status in ALLOWED_TRANSITIONS[prev.new_status], c.reference  # transitions légales
                assert cur.changed_at >= prev.changed_at
            assert hist[-1].new_status == c.status, c.reference
            assert hist[0].changed_at == c.created_at
            assert max(h.changed_at for h in hist) <= now                              # rien dans le futur
            assert c.updated_at >= c.created_at

            # cohérence statut / affectation / dates
            if c.status != Status.SUBMITTED:
                assert c.assigned_to_id is not None and c.priority is not None, c.reference
            if c.status in (Status.RESOLVED, Status.CLOSED):
                assert c.resolved_at is not None, c.reference
            if c.status in (Status.SUBMITTED, Status.ASSIGNED, Status.IN_PROGRESS):
                assert c.resolved_at is None, c.reference
            assert (c.closed_at is not None) == (c.status == Status.CLOSED), c.reference

            # un coordinateur n'agit que sur ses plaintes, un étudiant ne se résout pas lui-même
            comments = db.scalars(select(ComplaintComment).where(ComplaintComment.complaint_id == c.id)).all()
            for m in comments:
                if m.is_resolution:
                    assert db.get(User, m.author_id).role.value in ("COORDINATOR", "ADMIN")
            assert all(m.created_at <= now for m in comments)

        assert db.scalar(select(func.count()).select_from(Notification)
                         .where(Notification.complaint_id.in_([c.id for c in demo]))) > len(demo)


def test_demo_data_works_through_the_api(client):
    adm = auth_pwd(client, "jordan.lee")
    stats = client.get("/api/admin/stats", headers=adm).json()
    assert stats["total"] >= len(seed_demo.C) and set(stats["by_status"]) >= {s.value for s in Status}
    r = client.get("/api/admin/complaints?status=SUBMITTED&limit=5", headers=adm)
    assert int(r.headers["X-Total-Count"]) >= 10 and len(r.json()) == 5   # la pagination est testable

    coord = auth_pwd(client, "priya.naidoo")
    mine = client.get("/api/coordinator/complaints?limit=200", headers=coord).json()
    assert mine and all(c["assigned_to"]["username"] == "priya.naidoo" for c in mine)
    assert client.get("/api/coordinator/stats", headers=coord).json()["total"] == len(mine)

    stud = auth_pwd(client, "amara.okafor")
    own = client.get("/api/student/complaints?limit=200", headers=stud).json()
    assert own and all(c["student"]["username"] == "amara.okafor" for c in own)
    detail = client.get(f"/api/student/complaints/{own[0]['id']}", headers=stud).json()
    assert detail["history"]
    assert client.get("/api/student/notifications", headers=stud).json()

    # le workflow continue de fonctionner sur ces données : l'admin assigne une plainte non affectée
    titles = {c[0] for c in seed_demo.C}
    todo = next(c for c in client.get("/api/admin/complaints?unassigned=true&limit=200", headers=adm).json()
                if c["title"] in titles)
    coord_id = client.get("/auth/me", headers=coord).json()["id"]
    r = client.patch(f"/api/admin/complaints/{todo['id']}/assign", headers=adm,
                     json={"assigned_to_id": coord_id, "priority": "HIGH"})
    assert r.status_code == 200 and r.json()["status"] == "ASSIGNED"


def test_reset_removes_only_demo_data(client):
    with SessionLocal() as db:
        real = Complaint(reference="CMP-2000-9999", title="Real complaint", description="Not a demo complaint.",
                         category_id=1, student_id=db.scalar(select(User.id).where(User.username == "stud")))
        db.add(real)
        db.commit()
        real_id = real.id
        seed_demo.reset(db)
        assert _demo(db) == []
        assert db.get(Complaint, real_id) is not None                     # les données réelles sont intactes
        assert db.scalar(select(User).where(User.username == "amara.okafor")) is None
        assert db.scalar(select(User).where(User.username == "stud")) is not None
        seed_demo.load(db)                                                # rechargeable après un reset
        assert len(_demo(db)) == len(seed_demo.C)


def auth_pwd(client, username):
    r = client.post("/auth/login", data={"username": username, "password": seed_demo.DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
