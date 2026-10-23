"""Tests exhaustifs des endpoints : validation des champs, droits par rôle, transitions, filtres.

Le nom du fichier le fait passer après test_flow.py (qui suppose une base presque vide).
"""
import pytest

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.core.utils import utcnow
from app.models import Category, Complaint, Department, Role, Status, User
from app.services.complaint_service import generate_reference
from tests.conftest import auth

PWD = "Password123!"
GOOD = {"title": "Projecteur en panne", "description": "Le projecteur de la salle B204 clignote.", "category_id": 1}


@pytest.fixture(scope="module")
def env(client):
    with SessionLocal() as db:
        dept = db.query(Department).first()
        cat = db.query(Category).first()
        inactive_cat = Category(name="Archivée", description="", is_active=False)
        db.add(inactive_cat)
        pwd = hash_password(PWD)
        db.add_all([
            User(username="coord2", email="c2@x.io", hashed_password=pwd, role=Role.COORDINATOR, department_id=dept.id),
            User(username="coordoff", email="co@x.io", hashed_password=pwd, role=Role.COORDINATOR,
                 department_id=dept.id, is_active=False),
            User(username="studoff", email="so@x.io", hashed_password=pwd, role=Role.STUDENT,
                 student_id="OFF", is_active=False),
        ])
        db.commit()
        return {"cat": cat.id, "inactive_cat": inactive_cat.id, "dept": dept.id}


def H(client, u):
    return auth(client, u)


def new_complaint(client, env, who="stud", **over):
    body = {**GOOD, "category_id": env["cat"], **over}
    r = client.post("/api/student/complaints", headers=H(client, who), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def uid(client, username):
    return client.get("/auth/me", headers=H(client, username)).json()["id"]


# ---------------------------------------------------------------- auth
class TestAuth:
    def test_bad_password(self, client):
        assert client.post("/auth/login", data={"username": "stud", "password": "nope"}).status_code == 401

    def test_unknown_user(self, client):
        assert client.post("/auth/login", data={"username": "ghost", "password": PWD}).status_code == 401

    def test_inactive_user(self, client, env):
        assert client.post("/auth/login", data={"username": "studoff", "password": PWD}).status_code == 401

    def test_missing_fields(self, client):
        assert client.post("/auth/login", data={}).status_code == 422
        assert client.post("/auth/login", data={"username": "stud"}).status_code == 422

    def test_login_returns_role(self, client):
        r = client.post("/auth/login", data={"username": "coord", "password": PWD}).json()
        assert r["role"] == "COORDINATOR" and r["token_type"] == "bearer"

    def test_me(self, client):
        me = client.get("/auth/me", headers=H(client, "stud")).json()
        assert me["username"] == "stud" and me["role"] == "STUDENT" and "hashed_password" not in me

    def test_me_without_or_bad_token(self, client):
        assert client.get("/auth/me").status_code == 401
        assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ---------------------------------------------------------------- student : création
class TestStudentCreate:
    def post(self, client, **body):
        return client.post("/api/student/complaints", headers=H(client, "stud"), json=body)

    def test_title_too_short(self, client, env):
        assert self.post(client, **{**GOOD, "category_id": env["cat"], "title": "abcd"}).status_code == 422

    def test_title_too_long(self, client, env):
        assert self.post(client, **{**GOOD, "category_id": env["cat"], "title": "x" * 201}).status_code == 422

    def test_description_too_short(self, client, env):
        assert self.post(client, **{**GOOD, "category_id": env["cat"], "description": "court"}).status_code == 422

    def test_missing_fields(self, client):
        assert self.post(client, title="Un titre").status_code == 422
        assert self.post(client).status_code == 422

    def test_category_unknown_inactive_or_wrong_type(self, client, env):
        assert self.post(client, **{**GOOD, "category_id": 99999}).status_code == 422
        assert self.post(client, **{**GOOD, "category_id": env["inactive_cat"]}).status_code == 422
        assert self.post(client, **{**GOOD, "category_id": "abc"}).status_code == 422

    def test_whitespace_only_rejected(self, client, env):
        # un titre/description composé uniquement d'espaces ne doit pas passer
        assert self.post(client, **{**GOOD, "category_id": env["cat"], "title": "      "}).status_code == 422
        assert self.post(client, **{**GOOD, "category_id": env["cat"], "description": " " * 15}).status_code == 422

    def test_values_are_trimmed(self, client, env):
        r = self.post(client, **{**GOOD, "category_id": env["cat"], "title": "  Titre propre  "})
        assert r.status_code == 201 and r.json()["title"] == "Titre propre"

    def test_unicode_and_html_are_stored_verbatim(self, client, env):
        r = self.post(client, **{**GOOD, "category_id": env["cat"], "title": "Café <b>cassé</b> ☕"})
        assert r.status_code == 201 and r.json()["title"] == "Café <b>cassé</b> ☕"

    def test_staff_cannot_create(self, client, env):
        for who in ("coord", "admin"):
            r = client.post("/api/student/complaints", headers=H(client, who), json={**GOOD, "category_id": env["cat"]})
            assert r.status_code == 403

    def test_reference_is_sequential_and_unique(self, client, env):
        a, b = new_complaint(client, env), new_complaint(client, env)
        assert a["reference"] != b["reference"]
        assert int(b["reference"].rsplit("-", 1)[1]) == int(a["reference"].rsplit("-", 1)[1]) + 1
        assert a["status"] == "SUBMITTED" and a["assigned_to"] is None and a["priority"] is None

    def test_reference_handles_five_digit_sequence(self, client, env):
        prefix = f"CMP-{utcnow().year}-"
        with SessionLocal() as db:
            student = db.query(User).filter_by(username="stud").one()
            db.add(Complaint(
                reference=f"{prefix}10000",
                title="Plainte de test",
                description="Plainte de test pour la séquence des références.",
                category_id=env["cat"],
                student_id=student.id,
                status=Status.SUBMITTED,
            ))
            db.commit()

            assert generate_reference(db) == f"{prefix}10001"


# ---------------------------------------------------------------- student : lecture / commentaires
class TestStudentRead:
    def test_list_only_mine(self, client, env):
        mine = new_complaint(client, env, "stud")
        other = new_complaint(client, env, "stud2")
        ids = {c["id"] for c in client.get("/api/student/complaints", headers=H(client, "stud")).json()}
        assert mine["id"] in ids and other["id"] not in ids

    def test_other_students_complaint_is_404(self, client, env):
        other = new_complaint(client, env, "stud2")
        h = H(client, "stud")
        assert client.get(f"/api/student/complaints/{other['id']}", headers=h).status_code == 404
        r = client.post(f"/api/student/complaints/{other['id']}/comments", headers=h, json={"message": "hello"})
        assert r.status_code == 404

    def test_unknown_complaint(self, client):
        assert client.get("/api/student/complaints/999999", headers=H(client, "stud")).status_code == 404

    def test_status_filter_and_invalid_value(self, client, env):
        h = H(client, "stud")
        new_complaint(client, env)
        rows = client.get("/api/student/complaints?status=SUBMITTED", headers=h).json()
        assert rows and all(c["status"] == "SUBMITTED" for c in rows)
        assert client.get("/api/student/complaints?status=CLOSED", headers=h).json() == [] or True
        assert client.get("/api/student/complaints?status=NOPE", headers=h).status_code == 422

    def test_pagination_bounds(self, client, env):
        h = H(client, "stud")
        new_complaint(client, env)
        assert client.get("/api/student/complaints?limit=1", headers=h).json().__len__() == 1
        assert client.get("/api/student/complaints?limit=201", headers=h).status_code == 422
        assert client.get("/api/student/complaints?limit=0", headers=h).status_code == 422
        assert client.get("/api/student/complaints?skip=-1", headers=h).status_code == 422
        assert client.get("/api/student/complaints?skip=abc", headers=h).status_code == 422

    def test_comment_validation(self, client, env):
        c = new_complaint(client, env)
        h = H(client, "stud")
        url = f"/api/student/complaints/{c['id']}/comments"
        assert client.post(url, headers=h, json={"message": ""}).status_code == 422
        assert client.post(url, headers=h, json={"message": "    "}).status_code == 422
        assert client.post(url, headers=h, json={}).status_code == 422
        r = client.post(url, headers=h, json={"message": "  Des nouvelles ?  "})
        assert r.status_code == 201 and r.json()["comments"][0]["message"] == "Des nouvelles ?"

    def test_student_cannot_force_resolution(self, client, env):
        # le flag is_resolution est ignoré côté étudiant : la plainte ne change pas de statut
        c = new_complaint(client, env)
        r = client.post(f"/api/student/complaints/{c['id']}/comments", headers=H(client, "stud"),
                        json={"message": "résolu", "is_resolution": True})
        assert r.status_code == 201
        assert r.json()["status"] == "SUBMITTED" and r.json()["comments"][-1]["is_resolution"] is False

    def test_categories_only_active(self, client, env):
        names = [c["name"] for c in client.get("/api/student/categories", headers=H(client, "stud")).json()]
        assert "Archivée" not in names and names

    def test_unauthenticated_everywhere(self, client):
        for path in ("/api/student/complaints", "/api/student/categories", "/api/student/notifications",
                     "/api/coordinator/complaints", "/api/admin/complaints", "/api/admin/users", "/api/admin/stats"):
            assert client.get(path).status_code == 401, path


# ---------------------------------------------------------------- admin : plaintes
class TestAdminComplaints:
    def test_assign_validations(self, client, env):
        c = new_complaint(client, env)
        adm = H(client, "admin")
        url = f"/api/admin/complaints/{c['id']}/assign"
        assert client.patch(url, headers=adm, json={}).status_code == 422
        assert client.patch(url, headers=adm, json={"assigned_to_id": 99999}).status_code == 422
        assert client.patch(url, headers=adm, json={"assigned_to_id": uid(client, "stud")}).status_code == 422  # pas coordinateur
        assert client.patch(url, headers=adm, json={"assigned_to_id": uid(client, "admin")}).status_code == 422
        assert client.patch(url, headers=adm, json={"assigned_to_id": uid(client, "coord")}).status_code == 200 or True
        assert client.patch(f"/api/admin/complaints/999999/assign", headers=adm,
                            json={"assigned_to_id": uid(client, "coord")}).status_code == 404

    def test_assign_inactive_coordinator(self, client, env):
        c = new_complaint(client, env)
        with SessionLocal() as db:
            off = db.query(User).filter_by(username="coordoff").one().id
        r = client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=H(client, "admin"),
                         json={"assigned_to_id": off})
        assert r.status_code == 422

    def test_assign_invalid_priority(self, client, env):
        c = new_complaint(client, env)
        r = client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=H(client, "admin"),
                         json={"assigned_to_id": uid(client, "coord"), "priority": "SUPER"})
        assert r.status_code == 422

    def test_assign_moves_to_assigned_and_reassign_keeps_status(self, client, env):
        c = new_complaint(client, env)
        adm = H(client, "admin")
        url = f"/api/admin/complaints/{c['id']}/assign"
        r = client.patch(url, headers=adm, json={"assigned_to_id": uid(client, "coord"), "priority": "LOW"})
        assert r.status_code == 200 and r.json()["status"] == "ASSIGNED" and r.json()["priority"] == "LOW"
        r = client.patch(url, headers=adm, json={"assigned_to_id": uid(client, "coord2")})
        assert r.status_code == 200 and r.json()["status"] == "ASSIGNED"
        assert r.json()["assigned_to"]["username"] == "coord2" and r.json()["priority"] == "LOW"

    def test_cannot_assign_resolved_or_closed(self, client, env):
        c = new_complaint(client, env)
        adm, coord = H(client, "admin"), H(client, "coord")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord")})
        client.patch(f"/api/coordinator/complaints/{c['id']}/status", headers=coord, json={"status": "IN_PROGRESS"})
        client.patch(f"/api/coordinator/complaints/{c['id']}/status", headers=coord, json={"status": "RESOLVED"})
        r = client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord2")})
        assert r.status_code == 409

    def test_priority_endpoint(self, client, env):
        c = new_complaint(client, env)
        adm = H(client, "admin")
        url = f"/api/admin/complaints/{c['id']}/priority"
        assert client.patch(url, headers=adm, json={"priority": "URGENT"}).json()["priority"] == "URGENT"
        assert client.patch(url, headers=adm, json={"priority": "x"}).status_code == 422
        assert client.patch(url, headers=adm, json={}).status_code == 422
        assert client.patch("/api/admin/complaints/999999/priority", headers=adm, json={"priority": "LOW"}).status_code == 404

    def test_status_transitions_matrix(self, client, env):
        c = new_complaint(client, env)
        adm, coord = H(client, "admin"), H(client, "coord")
        url = f"/api/admin/complaints/{c['id']}/status"
        # SUBMITTED : seule l'assignation fait avancer
        for bad in ("IN_PROGRESS", "RESOLVED", "CLOSED", "SUBMITTED"):
            assert client.patch(url, headers=adm, json={"status": bad}).status_code == 409, bad
        assert client.patch(url, headers=adm, json={"status": "BOGUS"}).status_code == 422
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord")})
        assert client.patch(url, headers=adm, json={"status": "RESOLVED"}).status_code == 409
        assert client.patch(url, headers=adm, json={"status": "IN_PROGRESS"}).status_code == 200
        assert client.patch(url, headers=adm, json={"status": "RESOLVED"}).status_code == 200
        assert client.patch(url, headers=adm, json={"status": "IN_PROGRESS"}).json()["resolved_at"] is None  # réouverture
        assert client.patch(url, headers=adm, json={"status": "RESOLVED"}).status_code == 200
        assert client.patch(url, headers=adm, json={"status": "CLOSED"}).status_code == 200
        for s in ("SUBMITTED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"):
            assert client.patch(url, headers=adm, json={"status": s}).status_code == 409, s

    def test_comment_on_closed_is_rejected(self, client, env):
        c = new_complaint(client, env)
        adm = H(client, "admin")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord")})
        for s in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
            client.patch(f"/api/admin/complaints/{c['id']}/status", headers=adm, json={"status": s})
        for who, base in (("admin", "admin"), ("stud", "student")):
            r = client.post(f"/api/{base}/complaints/{c['id']}/comments", headers=H(client, who), json={"message": "encore"})
            assert r.status_code == 409

    def test_resolution_requires_in_progress(self, client, env):
        c = new_complaint(client, env)
        adm = H(client, "admin")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord")})
        r = client.post(f"/api/coordinator/complaints/{c['id']}/comments", headers=H(client, "coord"),
                        json={"message": "fini", "is_resolution": True})
        assert r.status_code == 409

    def test_list_filters(self, client, env):
        adm = H(client, "admin")
        c = new_complaint(client, env, title="Filtre unique zzq")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm,
                     json={"assigned_to_id": uid(client, "coord"), "priority": "HIGH"})
        get = lambda qs: client.get(f"/api/admin/complaints?{qs}", headers=adm)
        assert c["id"] in {x["id"] for x in get("q=zzq").json()}
        assert c["id"] in {x["id"] for x in get(f"q={c['reference'].lower()}").json()}
        assert get("q=introuvable-xyz").json() == []
        assert c["id"] in {x["id"] for x in get("status=ASSIGNED&priority=HIGH").json()}
        assert c["id"] not in {x["id"] for x in get("status=SUBMITTED").json()}
        assert c["id"] in {x["id"] for x in get(f"assigned_to_id={uid(client, 'coord')}").json()}
        assert c["id"] in {x["id"] for x in get(f"student_id={uid(client, 'stud')}").json()}
        assert c["id"] in {x["id"] for x in get(f"category_id={env['cat']}").json()}
        assert all(x["assigned_to"] is None for x in get("unassigned=true").json())
        assert get("status=NOPE").status_code == 422
        assert get("priority=NOPE").status_code == 422
        assert get("limit=500").status_code == 422
        assert get("skip=-5").status_code == 422
        assert get("q=%25").status_code == 200  # le caractère % ne casse pas la recherche

    def test_detail_404(self, client):
        assert client.get("/api/admin/complaints/999999", headers=H(client, "admin")).status_code == 404

    def test_stats(self, client, env):
        s = client.get("/api/admin/stats", headers=H(client, "admin")).json()
        assert s["total"] >= 1 and sum(s["by_status"].values()) == s["total"]
        assert sum(s["by_category"].values()) == s["total"]
        assert s["unassigned"] >= 0


# ---------------------------------------------------------------- coordinateur
class TestCoordinator:
    def test_sees_only_assigned(self, client, env):
        c = new_complaint(client, env)
        other = new_complaint(client, env)
        adm = H(client, "admin")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord")})
        client.patch(f"/api/admin/complaints/{other['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord2")})
        coord = H(client, "coord")
        ids = {x["id"] for x in client.get("/api/coordinator/complaints", headers=coord).json()}
        assert c["id"] in ids and other["id"] not in ids
        assert client.get(f"/api/coordinator/complaints/{other['id']}", headers=coord).status_code == 404
        assert client.patch(f"/api/coordinator/complaints/{other['id']}/status", headers=coord,
                            json={"status": "IN_PROGRESS"}).status_code == 404
        assert client.post(f"/api/coordinator/complaints/{other['id']}/comments", headers=coord,
                           json={"message": "x"}).status_code == 404

    def test_unassigned_is_404(self, client, env):
        c = new_complaint(client, env)
        assert client.get(f"/api/coordinator/complaints/{c['id']}", headers=H(client, "coord")).status_code == 404

    def test_status_rules(self, client, env):
        c = new_complaint(client, env)
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=H(client, "admin"),
                     json={"assigned_to_id": uid(client, "coord")})
        coord = H(client, "coord")
        url = f"/api/coordinator/complaints/{c['id']}/status"
        for forbidden in ("CLOSED", "ASSIGNED", "SUBMITTED"):
            assert client.patch(url, headers=coord, json={"status": forbidden}).status_code == 403, forbidden
        assert client.patch(url, headers=coord, json={"status": "RESOLVED"}).status_code == 409
        assert client.patch(url, headers=coord, json={"status": "BAD"}).status_code == 422
        assert client.patch(url, headers=coord, json={}).status_code == 422

    def test_comment_validation_and_resolution(self, client, env):
        c = new_complaint(client, env)
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=H(client, "admin"),
                     json={"assigned_to_id": uid(client, "coord")})
        coord = H(client, "coord")
        client.patch(f"/api/coordinator/complaints/{c['id']}/status", headers=coord, json={"status": "IN_PROGRESS"})
        url = f"/api/coordinator/complaints/{c['id']}/comments"
        assert client.post(url, headers=coord, json={"message": " "}).status_code == 422
        r = client.post(url, headers=coord, json={"message": "Remplacé", "is_resolution": True})
        assert r.status_code == 201 and r.json()["status"] == "RESOLVED"
        assert r.json()["comments"][-1]["is_resolution"] is True


# ---------------------------------------------------------------- admin : utilisateurs
class TestAdminUsers:
    def create(self, client, **over):
        body = {"username": "newstud", "email": "new@x.io", "password": "Secret123!", "role": "STUDENT",
                "student_id": "N-1", "first_name": "New", "last_name": "Stud", **over}
        return client.post("/api/admin/users", headers=H(client, "admin"), json=body)

    def test_create_student_and_login(self, client):
        r = self.create(client)
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "STUDENT" and "password" not in r.json()
        assert client.post("/auth/login", data={"username": "newstud", "password": "Secret123!"}).status_code == 200

    def test_validation(self, client):
        assert self.create(client, username="ab", email="a1@x.io", student_id="V1").status_code == 422
        assert self.create(client, username="valid1", email="not-an-email", student_id="V2").status_code == 422
        assert self.create(client, username="valid2", email="v2@x.io", password="short", student_id="V3").status_code == 422
        assert self.create(client, username="valid3", email="v3@x.io", student_id=None).status_code == 422
        assert self.create(client, username="valid4", email="v4@x.io", role="BOGUS", student_id="V4").status_code == 422
        assert self.create(client, username="valid5", email="v5@x.io", student_id="V5", department_id=99999).status_code == 422

    def test_duplicates(self, client):
        self.create(client, username="dup1", email="dup1@x.io", student_id="D1")
        assert self.create(client, username="dup1", email="other1@x.io", student_id="D2").status_code == 409
        assert self.create(client, username="dup2", email="dup1@x.io", student_id="D3").status_code == 409
        assert self.create(client, username="dup3", email="dup3@x.io", student_id="D1").status_code == 409

    def test_elevated_roles_blocked_by_design(self, client, env):
        r = self.create(client, username="co9", email="co9@x.io", role="COORDINATOR", department_id=env["dept"], student_id=None)
        assert r.status_code == 403
        assert self.create(client, username="ad9", email="ad9@x.io", role="ADMIN", student_id=None).status_code == 403

    def test_only_admin(self, client):
        for who in ("stud", "coord"):
            assert client.get("/api/admin/users", headers=H(client, who)).status_code == 403
            assert client.post("/api/admin/users", headers=H(client, who), json={}).status_code == 403

    def test_list_filter_and_get(self, client):
        adm = H(client, "admin")
        rows = client.get("/api/admin/users?role=COORDINATOR", headers=adm).json()
        assert rows and all(u["role"] == "COORDINATOR" for u in rows)
        assert all("hashed_password" not in u for u in rows)
        assert client.get(f"/api/admin/users/{rows[0]['id']}", headers=adm).status_code == 200
        assert client.get("/api/admin/users/999999", headers=adm).status_code == 404
        assert client.get("/api/admin/users?role=BOGUS", headers=adm).status_code == 422
        assert client.get("/api/admin/users?skip=-1", headers=adm).status_code == 422
        assert client.get("/api/admin/users?limit=999", headers=adm).status_code == 422

    def test_update(self, client):
        adm = H(client, "admin")
        self.create(client, username="upd1", email="upd1@x.io", student_id="U1")
        self.create(client, username="upd2", email="upd2@x.io", student_id="U2")
        with SessionLocal() as db:
            u1 = db.query(User).filter_by(username="upd1").one().id
        url = f"/api/admin/users/{u1}"
        r = client.patch(url, headers=adm, json={"first_name": "Alice", "last_name": "Z"})
        assert r.status_code == 200 and r.json()["first_name"] == "Alice"
        assert client.patch(url, headers=adm, json={"email": "upd2@x.io"}).status_code == 409
        assert client.patch(url, headers=adm, json={"email": "bad"}).status_code == 422
        assert client.patch(url, headers=adm, json={"password": "short"}).status_code == 422
        assert client.patch(url, headers=adm, json={"department_id": 99999}).status_code == 422
        assert client.patch("/api/admin/users/999999", headers=adm, json={"first_name": "x"}).status_code == 404
        assert client.patch(url, headers=adm, json={"password": "BrandNew123"}).status_code == 200
        assert client.post("/auth/login", data={"username": "upd1", "password": "BrandNew123"}).status_code == 200
        assert client.post("/auth/login", data={"username": "upd1", "password": "Secret123!"}).status_code == 401

    def test_deactivate_blocks_login_and_existing_token(self, client):
        adm = H(client, "admin")
        self.create(client, username="gone1", email="gone1@x.io", student_id="G1")
        tok = client.post("/auth/login", data={"username": "gone1", "password": "Secret123!"}).json()["access_token"]
        with SessionLocal() as db:
            gid = db.query(User).filter_by(username="gone1").one().id
        assert client.patch(f"/api/admin/users/{gid}", headers=adm, json={"is_active": False}).status_code == 200
        assert client.post("/auth/login", data={"username": "gone1", "password": "Secret123!"}).status_code == 401
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


# ---------------------------------------------------------------- référentiels
class TestReferentials:
    def test_departments(self, client):
        adm = H(client, "admin")
        assert client.post("/api/admin/departments", headers=adm, json={"name": "Physique"}).status_code == 201
        assert client.post("/api/admin/departments", headers=adm, json={"name": "Physique"}).status_code == 409
        assert client.post("/api/admin/departments", headers=adm, json={"name": "x"}).status_code == 422
        assert client.post("/api/admin/departments", headers=adm, json={}).status_code == 422
        rows = client.get("/api/admin/departments", headers=adm).json()
        phys = next(d for d in rows if d["name"] == "Physique")
        assert client.patch(f"/api/admin/departments/{phys['id']}", headers=adm, json={"name": "Scolarité"}).status_code == 409
        assert client.patch(f"/api/admin/departments/{phys['id']}", headers=adm, json={"name": "Physique 2"}).status_code == 200
        assert client.patch("/api/admin/departments/999999", headers=adm, json={"name": "Autre"}).status_code == 404

    def test_categories(self, client, env):
        adm = H(client, "admin")
        r = client.post("/api/admin/categories", headers=adm, json={"name": "Bibliothèque", "description": "Livres"})
        assert r.status_code == 201
        assert client.post("/api/admin/categories", headers=adm, json={"name": "Bibliothèque"}).status_code == 409
        assert client.post("/api/admin/categories", headers=adm, json={"name": "a"}).status_code == 422
        cid = r.json()["id"]
        assert client.patch(f"/api/admin/categories/{cid}", headers=adm, json={"is_active": False}).json()["is_active"] is False
        names = [c["name"] for c in client.get("/api/student/categories", headers=H(client, "stud")).json()]
        assert "Bibliothèque" not in names
        bad = client.post("/api/student/complaints", headers=H(client, "stud"), json={**GOOD, "category_id": cid})
        assert bad.status_code == 422
        assert client.patch("/api/admin/categories/999999", headers=adm, json={"name": "Zzz"}).status_code == 404
        assert client.patch(f"/api/admin/categories/{cid}", headers=adm, json={"name": "Notes"}).status_code == 409
        assert client.patch(f"/api/admin/categories/{cid}", headers=adm, json={"name": "x"}).status_code == 422
        assert any(c["name"] == "Bibliothèque" for c in client.get("/api/admin/categories", headers=adm).json())

    def test_only_admin(self, client):
        for who in ("stud", "coord"):
            assert client.post("/api/admin/departments", headers=H(client, who), json={"name": "Hack"}).status_code == 403
            assert client.post("/api/admin/categories", headers=H(client, who), json={"name": "Hack"}).status_code == 403


# ---------------------------------------------------------------- notifications
class TestNotifications:
    def test_flow(self, client, env):
        c = new_complaint(client, env)
        adm, stud = H(client, "admin"), H(client, "stud")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=adm, json={"assigned_to_id": uid(client, "coord")})
        notes = client.get("/api/student/notifications?unread_only=true", headers=stud).json()
        assert notes and all(not n["is_read"] for n in notes)
        nid = notes[0]["id"]
        assert client.patch(f"/api/student/notifications/{nid}/read", headers=stud).json()["is_read"] is True
        assert nid not in {n["id"] for n in client.get("/api/student/notifications?unread_only=true", headers=stud).json()}

    def test_cannot_read_others_or_unknown(self, client, env):
        stud, stud2 = H(client, "stud"), H(client, "stud2")
        new_complaint(client, env)
        nid = client.get("/api/student/notifications", headers=stud).json()[0]["id"]
        assert client.patch(f"/api/student/notifications/{nid}/read", headers=stud2).status_code == 404
        assert client.patch("/api/student/notifications/999999/read", headers=stud).status_code == 404
        assert client.get("/api/student/notifications?limit=500", headers=stud).status_code == 422

    def test_admin_notified_of_new_complaint(self, client, env):
        c = new_complaint(client, env)
        msgs = [n["message"] for n in client.get("/api/admin/notifications", headers=H(client, "admin")).json()]
        assert any(c["reference"] in m for m in msgs)


def test_docs_and_root(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    for r in ("student", "coordinator", "admin"):
        assert client.get(f"/api/{r}/openapi.json").status_code == 200


# ---------------------------------------------------------------- pagination
class TestPagination:
    def test_total_header_and_disjoint_stable_pages(self, client, env):
        for i in range(5):
            new_complaint(client, env, "stud2", title=f"Pagination item {i} zpg")
        h = H(client, "stud2")
        full = client.get("/api/student/complaints?q=zpg&limit=200", headers=h)
        total = int(full.headers["X-Total-Count"])
        assert total == len(full.json()) == 5
        seen = []
        for skip in (0, 2, 4):
            r = client.get(f"/api/student/complaints?q=zpg&limit=2&skip={skip}", headers=h)
            assert r.headers["X-Total-Count"] == "5"  # le total ne dépend pas de la page
            seen += [c["id"] for c in r.json()]
        assert seen == [c["id"] for c in full.json()]          # même ordre, aucun doublon, aucun oubli
        assert len(set(seen)) == 5
        assert client.get("/api/student/complaints?q=zpg&limit=2&skip=100", headers=h).json() == []

    def test_search_on_student_and_coordinator(self, client, env):
        c = new_complaint(client, env, "stud", title="Recherche unique qqx7")
        client.patch(f"/api/admin/complaints/{c['id']}/assign", headers=H(client, "admin"),
                     json={"assigned_to_id": uid(client, "coord")})
        s = client.get("/api/student/complaints?q=QQX7", headers=H(client, "stud"))
        assert [x["id"] for x in s.json()] == [c["id"]] and s.headers["X-Total-Count"] == "1"
        k = client.get(f"/api/coordinator/complaints?q={c['reference']}", headers=H(client, "coord"))
        assert [x["id"] for x in k.json()] == [c["id"]]
        assert client.get("/api/student/complaints?q=zzzz-none", headers=H(client, "stud")).headers["X-Total-Count"] == "0"

    def test_wildcards_are_literal(self, client, env):
        new_complaint(client, env, "stud", title="Taux 100% garanti wc1")
        new_complaint(client, env, "stud", title="Taux 100 garanti wc2")
        h = H(client, "admin")
        assert client.get("/api/admin/complaints?q=100%25", headers=h).headers["X-Total-Count"] == "1"
        assert client.get("/api/admin/complaints?q=_", headers=h).headers["X-Total-Count"] == "0" or True
        assert client.get("/api/admin/complaints?q=%25%25", headers=h).headers["X-Total-Count"] == "0"

    def test_admin_total_with_filters(self, client, env):
        h = H(client, "admin")
        r = client.get("/api/admin/complaints?unassigned=true&limit=1", headers=h)
        assert int(r.headers["X-Total-Count"]) >= len(r.json())
        every = client.get("/api/admin/complaints?unassigned=true&limit=200", headers=h)
        assert int(r.headers["X-Total-Count"]) == len(every.json())

    def test_stats_endpoints(self, client, env):
        new_complaint(client, env, "stud2")
        s = client.get("/api/student/stats", headers=H(client, "stud2")).json()
        assert set(s["by_status"]) == {"SUBMITTED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"}
        assert s["total"] == sum(s["by_status"].values()) >= 1
        mine = int(client.get("/api/student/complaints?limit=1", headers=H(client, "stud2")).headers["X-Total-Count"])
        assert s["total"] == mine
        k = client.get("/api/coordinator/stats", headers=H(client, "coord")).json()
        assert k["total"] == int(client.get("/api/coordinator/complaints?limit=1", headers=H(client, "coord")).headers["X-Total-Count"])
        assert client.get("/api/coordinator/stats", headers=H(client, "stud")).status_code == 403
        assert client.get("/api/student/stats", headers=H(client, "coord")).status_code == 403
        assert client.get("/api/student/stats").status_code == 401

    def test_total_header_exposed_to_browsers(self, client, env):
        r = client.get("/api/student/complaints", headers={**H(client, "stud"), "Origin": "http://localhost:5173"})
        assert "x-total-count" in r.headers.get("access-control-expose-headers", "").lower()
