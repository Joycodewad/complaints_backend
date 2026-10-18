from tests.conftest import auth


def test_full_lifecycle(client):
    adm, coord, stud = auth(client, "admin"), auth(client, "coord"), auth(client, "stud")

    cats = client.get("/api/student/categories", headers=stud).json()
    r = client.post("/api/student/complaints", headers=stud, json={
        "title": "Note erronée", "description": "Ma note est incorrecte depuis l'examen.", "category_id": cats[0]["id"]})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["reference"].startswith("CMP-") and c["reference"].endswith("-0001")
    assert c["status"] == "SUBMITTED"
    cid = c["id"]

    coord_id = client.get("/auth/me", headers=coord).json()["id"]
    r = client.patch(f"/api/admin/complaints/{cid}/assign", headers=adm, json={"assigned_to_id": coord_id, "priority": "HIGH"})
    assert r.status_code == 200 and r.json()["status"] == "ASSIGNED"

    # le coordinateur ne peut pas clôturer, ni sauter d'étape
    assert client.patch(f"/api/coordinator/complaints/{cid}/status", headers=coord, json={"status": "CLOSED"}).status_code == 403
    assert client.patch(f"/api/coordinator/complaints/{cid}/status", headers=coord, json={"status": "RESOLVED"}).status_code == 409

    assert client.patch(f"/api/coordinator/complaints/{cid}/status", headers=coord, json={"status": "IN_PROGRESS"}).status_code == 200
    r = client.post(f"/api/coordinator/complaints/{cid}/comments", headers=coord,
                    json={"message": "Note corrigée.", "is_resolution": True})
    assert r.status_code == 201 and r.json()["status"] == "RESOLVED" and r.json()["resolved_at"]

    r = client.patch(f"/api/admin/complaints/{cid}/status", headers=adm, json={"status": "CLOSED"})
    assert r.status_code == 200 and r.json()["closed_at"]

    detail = client.get(f"/api/student/complaints/{cid}", headers=stud).json()
    assert [h["new_status"] for h in detail["history"]] == ["SUBMITTED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    assert len(client.get("/api/student/notifications", headers=stud).json()) >= 3
    assert client.get("/api/admin/stats", headers=adm).json()["total"] == 1


def test_role_isolation(client):
    adm, stud, stud2 = auth(client, "admin"), auth(client, "stud"), auth(client, "stud2")
    assert client.get("/api/admin/users", headers=stud).status_code == 403
    assert client.get("/api/coordinator/complaints", headers=stud).status_code == 403
    assert client.get("/api/student/complaints", headers=adm).status_code == 403
    assert client.get("/api/student/complaints/1", headers=stud2).status_code == 404  # pas la sienne
    assert client.get("/api/student/complaints").status_code == 401


def test_swagger_per_role(client):
    paths = {r: set(client.get(f"/api/{r}/openapi.json").json()["paths"]) for r in ("student", "coordinator", "admin")}
    assert "/users" in paths["admin"] and "/users" not in paths["student"]
    assert "/complaints/{complaint_id}/assign" in paths["admin"]
    assert "/complaints/{complaint_id}/assign" not in paths["coordinator"]
    for r in paths:
        assert client.get(f"/api/{r}/docs").status_code == 200
