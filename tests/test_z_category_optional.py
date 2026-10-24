"""Release 1 : l'étudiant ne choisit pas de catégorie ; l'administrateur catégorisera plus tard (story 6, sprint 3)."""
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Complaint
from scripts import seed_demo
from tests.conftest import auth

BODY = {"title": "Projector keeps flickering", "description": "It flickers ten minutes after being switched on."}


def create(client, who="stud", **extra):
    return client.post("/api/student/complaints", headers=auth(client, who), json={**BODY, **extra})


def test_student_can_submit_without_category(client):
    r = create(client)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["category"] is None and c["status"] == "SUBMITTED"


def test_explicit_null_is_accepted(client):
    assert create(client, category_id=None).status_code == 201


def test_a_provided_category_is_still_validated(client):
    cats = client.get("/api/student/categories", headers=auth(client, "stud")).json()
    assert create(client, category_id=cats[0]["id"]).json()["category"]["id"] == cats[0]["id"]
    assert create(client, category_id=999999).status_code == 422
    assert create(client, category_id="abc").status_code == 422


def test_uncategorized_complaints_are_visible_to_every_role(client):
    c = create(client).json()
    adm, stud = auth(client, "admin"), auth(client, "stud")
    assert client.get(f"/api/student/complaints/{c['id']}", headers=stud).json()["category"] is None
    assert client.get(f"/api/admin/complaints/{c['id']}", headers=adm).json()["category"] is None
    rows = client.get("/api/student/complaints?limit=200", headers=stud).json()
    assert any(r["id"] == c["id"] and r["category"] is None for r in rows)
    coord_id = client.get("/auth/me", headers=auth(client, "coord")).json()["id"]
    r = client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": coord_id})
    assert r.status_code == 200 and r.json()["category"] is None          # le workflow n'a pas besoin de catégorie
    mine = client.get(f"/api/coordinator/complaints/{c['id']}", headers=auth(client, "coord")).json()
    assert mine["category"] is None


def test_stats_group_uncategorized(client):
    create(client)
    s = client.get("/api/admin/stats", headers=auth(client, "admin")).json()
    assert s["by_category"].get("Uncategorized", 0) >= 1
    assert sum(s["by_category"].values()) == s["total"]


def test_admin_category_filter_still_works(client):
    adm = auth(client, "admin")
    cat = client.get("/api/student/categories", headers=auth(client, "stud")).json()[0]["id"]
    c = create(client, category_id=cat).json()
    rows = client.get(f"/api/admin/complaints?category_id={cat}&limit=200", headers=adm).json()
    assert c["id"] in {r["id"] for r in rows} and all(r["category"]["id"] == cat for r in rows)


def test_demo_seed_is_uncategorized_by_default_and_categorized_on_demand(client):
    with SessionLocal() as db:
        seed_demo.reset(db)
        seed_demo.load(db)
        demo = db.scalars(select(Complaint).where(Complaint.attachment == seed_demo.MARKER)).all()
        assert demo and all(c.category_id is None for c in demo)
        seed_demo.reset(db)
        seed_demo.load(db, with_categories=True)
        demo = db.scalars(select(Complaint).where(Complaint.attachment == seed_demo.MARKER)).all()
        assert demo and all(c.category_id is not None for c in demo)
        seed_demo.reset(db)  # on laisse la base comme on l'a trouvée (sans données de démo)
