"""Sprint 1, stories 1 et 2 : gestion des comptes par l'administrateur et connexion par email."""
import pytest

from tests.conftest import auth

PWD = "Secret123!"


def adm(client):
    return auth(client, "admin")


def new_user(client, email, **over):
    body = {"email": email, "password": PWD, "first_name": "Test", "last_name": "User", "role": "STUDENT", **over}
    return client.post("/api/admin/users", headers=adm(client), json=body)


def login(client, ident, password=PWD):
    return client.post("/auth/login", data={"username": ident, "password": password})


# ---------------------------------------------------------------- story 2 : connexion par email
class TestLoginByEmail:
    def test_email_and_password(self, client):
        new_user(client, "login.one@univ.edu")
        r = login(client, "login.one@univ.edu")
        assert r.status_code == 200 and r.json()["role"] == "STUDENT"

    def test_email_is_case_insensitive_and_trimmed(self, client):
        new_user(client, "login.two@univ.edu")
        assert login(client, "  LOGIN.Two@Univ.EDU  ").status_code == 200

    def test_wrong_password_unknown_email_and_empty(self, client):
        new_user(client, "login.three@univ.edu")
        assert login(client, "login.three@univ.edu", "wrong-password").status_code == 401
        assert login(client, "nobody@univ.edu").status_code == 401
        assert client.post("/auth/login", data={"username": "login.three@univ.edu"}).status_code == 422
        assert client.post("/auth/login", data={}).status_code == 422

    def test_same_message_for_unknown_email_and_wrong_password(self, client):
        new_user(client, "login.four@univ.edu")
        a = login(client, "login.four@univ.edu", "bad-password-1").json()
        b = login(client, "ghost@univ.edu", "bad-password-1").json()
        assert a == b  # on ne révèle pas si le compte existe

    def test_deactivated_account_cannot_log_in(self, client):
        r = new_user(client, "login.five@univ.edu", is_active=False)
        assert r.status_code == 201 and r.json()["is_active"] is False
        assert login(client, "login.five@univ.edu").status_code == 401

    def test_each_role_lands_on_its_own_api(self, client):
        for email, role in (("role.s@univ.edu", "STUDENT"), ("role.c@univ.edu", "COORDINATOR"), ("role.a@univ.edu", "ADMIN")):
            new_user(client, email, role=role)
            token = login(client, email).json()
            assert token["role"] == role
        h = {"Authorization": f"Bearer {login(client, 'role.s@univ.edu').json()['access_token']}"}
        assert client.get("/api/student/complaints", headers=h).status_code == 200
        assert client.get("/api/admin/users", headers=h).status_code == 403            # un étudiant ne gère pas les comptes
        assert client.get("/api/coordinator/complaints", headers=h).status_code == 403

    def test_old_username_still_accepted(self, client):
        assert login(client, "stud", "Password123!").status_code == 200

    def test_me_returns_the_profile_without_secrets(self, client):
        new_user(client, "me.check@univ.edu", first_name="Mina", last_name="Check")
        token = login(client, "me.check@univ.edu").json()["access_token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
        assert me["email"] == "me.check@univ.edu" and me["first_name"] == "Mina" and "hashed_password" not in me


# ---------------------------------------------------------------- story 1 : gestion des comptes
class TestCreate:
    def test_full_form_name_email_role_status(self, client):
        r = new_user(client, "Create.One@Univ.edu", first_name="Amina", last_name="Diallo", role="COORDINATOR", is_active=True)
        assert r.status_code == 201, r.text
        u = r.json()
        assert u["email"] == "create.one@univ.edu"                        # email enregistré en minuscules
        assert (u["first_name"], u["last_name"], u["role"], u["is_active"]) == ("Amina", "Diallo", "COORDINATOR", True)
        assert "password" not in u and "hashed_password" not in u

    def test_username_is_derived_from_email_and_unique(self, client):
        a = new_user(client, "dup.name@univ.edu").json()
        b = new_user(client, "dup.name@other.edu").json()
        assert a["username"] == "dup.name" and b["username"] == "dup.name2"

    def test_no_student_id_or_department_required(self, client):
        assert new_user(client, "plain.student@univ.edu").status_code == 201
        assert new_user(client, "plain.coord@univ.edu", role="COORDINATOR").status_code == 201

    def test_field_validation(self, client):
        assert new_user(client, "not-an-email").status_code == 422
        assert new_user(client, "val.pw@univ.edu", password="short").status_code == 422
        assert new_user(client, "val.name@univ.edu", first_name="").status_code == 422
        assert new_user(client, "val.name2@univ.edu", first_name="   ").status_code == 422
        assert new_user(client, "val.role@univ.edu", role="SUPERUSER").status_code == 422
        assert new_user(client, "val.dept@univ.edu", role="COORDINATOR", department_id=999999).status_code == 422
        assert client.post("/api/admin/users", headers=adm(client), json={}).status_code == 422

    def test_duplicate_email_is_rejected_whatever_the_case(self, client):
        assert new_user(client, "unique.mail@univ.edu").status_code == 201
        assert new_user(client, "unique.mail@univ.edu").status_code == 409
        assert new_user(client, "UNIQUE.MAIL@UNIV.EDU").status_code == 409

    def test_only_administrators(self, client):
        stud = auth(client, "stud")
        coord = auth(client, "coord")
        for h in (stud, coord):
            assert client.post("/api/admin/users", headers=h, json={"email": "x@y.io", "password": PWD, "first_name": "X"}).status_code == 403
        assert client.post("/api/admin/users", json={}).status_code == 401


class TestUpdate:
    def make(self, client, email, **over):
        return new_user(client, email, **over).json()

    def test_edit_name_email_role_status(self, client):
        u = self.make(client, "edit.me@univ.edu")
        url = f"/api/admin/users/{u['id']}"
        r = client.patch(url, headers=adm(client), json={"first_name": "Zed", "last_name": "Edited", "email": "Edited.Me@univ.edu",
                                                         "role": "COORDINATOR", "is_active": False})
        assert r.status_code == 200, r.text
        j = r.json()
        assert (j["first_name"], j["last_name"], j["email"], j["role"], j["is_active"]) == ("Zed", "Edited", "edited.me@univ.edu", "COORDINATOR", False)
        assert login(client, "edited.me@univ.edu").status_code == 401        # désactivé
        client.patch(url, headers=adm(client), json={"is_active": True})
        assert login(client, "edited.me@univ.edu").status_code == 200        # réactivé

    def test_partial_update_and_nulls_do_not_erase_required_fields(self, client):
        u = self.make(client, "partial@univ.edu", first_name="Keep")
        url = f"/api/admin/users/{u['id']}"
        r = client.patch(url, headers=adm(client), json={"last_name": "Changed", "first_name": None, "email": None, "role": None})
        assert r.status_code == 200
        j = r.json()
        assert j["first_name"] == "Keep" and j["email"] == "partial@univ.edu" and j["role"] == "STUDENT" and j["last_name"] == "Changed"

    def test_validation_and_duplicates(self, client):
        a, b = self.make(client, "upd.a@univ.edu"), self.make(client, "upd.b@univ.edu")
        url = f"/api/admin/users/{a['id']}"
        assert client.patch(url, headers=adm(client), json={"email": "upd.b@univ.edu"}).status_code == 409
        assert client.patch(url, headers=adm(client), json={"email": "UPD.B@univ.edu"}).status_code == 409
        assert client.patch(url, headers=adm(client), json={"email": "upd.a@univ.edu"}).status_code == 200   # son propre email
        assert client.patch(url, headers=adm(client), json={"email": "nope"}).status_code == 422
        assert client.patch(url, headers=adm(client), json={"first_name": ""}).status_code == 422
        assert client.patch(url, headers=adm(client), json={"role": "BOSS"}).status_code == 422
        assert client.patch(url, headers=adm(client), json={"password": "short"}).status_code == 422
        assert client.patch("/api/admin/users/999999", headers=adm(client), json={"first_name": "X"}).status_code == 404

    def test_password_reset(self, client):
        u = self.make(client, "reset.pw@univ.edu")
        client.patch(f"/api/admin/users/{u['id']}", headers=adm(client), json={"password": "BrandNew#2026"})
        assert login(client, "reset.pw@univ.edu", "BrandNew#2026").status_code == 200
        assert login(client, "reset.pw@univ.edu").status_code == 401

    def test_empty_password_keeps_the_current_one(self, client):
        u = self.make(client, "keep.pw@univ.edu")
        r = client.patch(f"/api/admin/users/{u['id']}", headers=adm(client), json={"first_name": "Still"})
        assert r.status_code == 200 and login(client, "keep.pw@univ.edu").status_code == 200

    def test_an_administrator_cannot_lock_themselves_out(self, client):
        me = client.get("/auth/me", headers=adm(client)).json()
        url = f"/api/admin/users/{me['id']}"
        assert client.patch(url, headers=adm(client), json={"is_active": False}).status_code == 409
        assert client.patch(url, headers=adm(client), json={"role": "STUDENT"}).status_code == 409
        assert client.patch(url, headers=adm(client), json={"first_name": "Ada", "role": "ADMIN", "is_active": True}).status_code == 200
        assert login(client, "a@x.io", "Password123!").status_code == 200       # le compte admin fonctionne toujours

    def test_an_administrator_can_deactivate_another_administrator(self, client):
        other = self.make(client, "other.admin@univ.edu", role="ADMIN")
        r = client.patch(f"/api/admin/users/{other['id']}", headers=adm(client), json={"is_active": False})
        assert r.status_code == 200 and login(client, "other.admin@univ.edu").status_code == 401

    def test_deactivation_also_kills_the_existing_session(self, client):
        u = self.make(client, "kill.session@univ.edu")
        token = login(client, "kill.session@univ.edu").json()["access_token"]
        client.patch(f"/api/admin/users/{u['id']}", headers=adm(client), json={"is_active": False})
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


class TestList:
    def test_filters_search_and_total(self, client):
        for i in range(5):
            new_user(client, f"list.item{i}@univ.edu", first_name="Listed", last_name=f"Person{i}", role="COORDINATOR" if i < 2 else "STUDENT")
        new_user(client, "list.off@univ.edu", first_name="Listed", last_name="Off", is_active=False)
        h = adm(client)
        r = client.get("/api/admin/users?q=listed&limit=200", headers=h)
        assert int(r.headers["X-Total-Count"]) == len(r.json()) == 6
        assert len(client.get("/api/admin/users?q=Person3", headers=h).json()) == 1                  # par nom
        assert len(client.get("/api/admin/users?q=list.item4@", headers=h).json()) == 1             # par email
        assert all(u["role"] == "COORDINATOR" for u in client.get("/api/admin/users?q=listed&role=COORDINATOR", headers=h).json())
        off = client.get("/api/admin/users?q=listed&is_active=false", headers=h).json()
        assert [u["last_name"] for u in off] == ["Off"]
        assert int(client.get("/api/admin/users?q=listed&is_active=true", headers=h).headers["X-Total-Count"]) == 5

    def test_pagination_has_no_gaps_or_duplicates(self, client):
        h = adm(client)
        total = int(client.get("/api/admin/users?limit=1", headers=h).headers["X-Total-Count"])
        seen = []
        for skip in range(0, total, 7):
            seen += [u["id"] for u in client.get(f"/api/admin/users?skip={skip}&limit=7", headers=h).json()]
        assert len(seen) == total == len(set(seen))

    def test_search_wildcards_are_literal(self, client):
        h = adm(client)
        assert client.get("/api/admin/users?q=%25", headers=h).headers["X-Total-Count"] == "0"

    def test_invalid_parameters(self, client):
        h = adm(client)
        assert client.get("/api/admin/users?role=BOSS", headers=h).status_code == 422
        assert client.get("/api/admin/users?skip=-1", headers=h).status_code == 422
        assert client.get("/api/admin/users?limit=0", headers=h).status_code == 422

    def test_never_exposes_password_hashes(self, client):
        rows = client.get("/api/admin/users?limit=200", headers=adm(client)).json()
        assert rows and all("hashed_password" not in u and "password" not in u for u in rows)

    def test_only_administrators_can_list(self, client):
        for who in ("stud", "coord"):
            assert client.get("/api/admin/users", headers=auth(client, who)).status_code == 403
        assert client.get("/api/admin/users").status_code == 401
