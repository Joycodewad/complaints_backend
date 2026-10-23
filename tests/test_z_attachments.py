"""Pièces jointes : types réels, tailles, limites, droits, nettoyage."""
import struct
import zlib
from pathlib import Path

import pytest

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Attachment, Complaint
from tests.conftest import auth


def _png(extra: int = 0) -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"\x00\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"") + b"\0" * extra)


JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\0" * 40 + b"\xff\xd9"
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00" + b"\0" * 20
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\0" * 30
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\0" * 40
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"\0" * 40
WEBM = b"\x1aE\xdf\xa3" + b"\0" * 40
EXE = b"MZ\x90\x00" + b"\0" * 60
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\0" * 20


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    return tmp_path / "uploads"


@pytest.fixture(scope="module")
def cat(client):
    return client.get("/api/student/categories", headers=auth(client, "stud")).json()[0]["id"]


@pytest.fixture(scope="module")
def other_coord(client):
    from app.core.security import hash_password
    from app.models import Department, Role, User
    with SessionLocal() as db:
        if not db.query(User).filter_by(username="coord_att").first():
            db.add(User(username="coord_att", email="coord_att@x.io", hashed_password=hash_password("Password123!"),
                        role=Role.COORDINATOR, department_id=db.query(Department).first().id))
            db.commit()
    return "coord_att"


def make(client, cat, who="stud"):
    r = client.post("/api/student/complaints", headers=auth(client, who), json={
        "title": "Complaint with files", "description": "Needs pictures to be understood.", "category_id": cat})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def up(client, cid, files, who="stud"):
    return client.post(f"/api/student/complaints/{cid}/attachments", headers=auth(client, who), files=files)


def f(name, data, ctype="application/octet-stream"):
    return ("files", (name, data, ctype))


class TestUpload:
    def test_all_allowed_types(self, client, cat):
        cid = make(client, cat)
        r = up(client, cid, [f("a.png", _png()), f("b.jpg", JPEG), f("c.gif", GIF), f("d.webp", WEBP), f("e.mp4", MP4)])
        assert r.status_code == 201, r.text
        types = [a["content_type"] for a in r.json()["attachments"]]
        assert types == ["image/png", "image/jpeg", "image/gif", "image/webp", "video/mp4"]

    def test_mov_and_webm(self, client, cat):
        cid = make(client, cat)
        r = up(client, cid, [f("m.mov", MOV), f("w.webm", WEBM)])
        assert [a["content_type"] for a in r.json()["attachments"]] == ["video/quicktime", "video/webm"]

    def test_type_comes_from_content_not_from_client_header(self, client, cat):
        cid = make(client, cat)
        # un vrai PNG déclaré text/plain est accepté comme image/png
        r = up(client, cid, [f("photo.txt", _png(), "text/plain")])
        a = r.json()["attachments"][0]
        assert r.status_code == 201 and a["content_type"] == "image/png" and a["filename"] == "photo.png"

    @pytest.mark.parametrize("name,data,ctype", [
        ("virus.png", EXE, "image/png"),            # exécutable déguisé en image
        ("notes.txt", b"just some text", "text/plain"),
        ("evil.svg", SVG, "image/svg+xml"),         # SVG refusé (XSS)
        ("photo.heic", HEIC, "image/heic"),
        ("page.html", b"<html><script>1</script></html>", "text/html"),
    ])
    def test_rejects_other_content(self, client, cat, name, data, ctype):
        cid = make(client, cat)
        assert up(client, cid, [f(name, data, ctype)]).status_code == 415

    def test_empty_file(self, client, cat):
        cid = make(client, cat)
        assert up(client, cid, [f("empty.png", b"")]).status_code == 415  # aucune signature

    def test_no_file_and_wrong_encoding(self, client, cat):
        cid = make(client, cat)
        assert client.post(f"/api/student/complaints/{cid}/attachments", headers=auth(client, "stud")).status_code == 422
        r = client.post(f"/api/student/complaints/{cid}/attachments", headers=auth(client, "stud"), json={"files": []})
        assert r.status_code == 422

    def test_too_large(self, client, cat, monkeypatch):
        monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
        cid = make(client, cat)
        assert up(client, cid, [f("big.png", _png(extra=1024 * 1024 + 10))]).status_code == 413
        assert up(client, cid, [f("ok.png", _png(extra=1000))]).status_code == 201

    def test_max_files_per_complaint(self, client, cat):
        cid = make(client, cat)
        assert up(client, cid, [f(f"{i}.png", _png()) for i in range(5)]).status_code == 201
        r = up(client, cid, [f("sixth.png", _png())])
        assert r.status_code == 409 and "5" in r.json()["detail"]
        cid2 = make(client, cat)
        assert up(client, cid2, [f(f"{i}.png", _png()) for i in range(6)]).status_code == 409  # 6 d'un coup

    def test_all_or_nothing(self, client, cat, upload_dir):
        cid = make(client, cat)
        r = up(client, cid, [f("good.png", _png()), f("bad.png", EXE)])
        assert r.status_code == 415
        detail = client.get(f"/api/student/complaints/{cid}", headers=auth(client, "stud")).json()
        assert detail["attachments"] == []
        folder = upload_dir / str(cid)
        assert not folder.exists() or list(folder.iterdir()) == []   # aucun fichier orphelin

    def test_filename_is_sanitized_and_never_used_on_disk(self, client, cat, upload_dir):
        cid = make(client, cat)
        r = up(client, cid, [f("../../etc/passwd.png", _png()), f("C:\\Users\\me\\<script>.png", _png())])
        assert r.status_code == 201
        names = [a["filename"] for a in r.json()["attachments"]]
        assert names[0] == "passwd.png" and "/" not in names[1] and "\\" not in names[1] and "<" not in names[1]
        on_disk = {p.name for p in (upload_dir / str(cid)).iterdir()}
        assert len(on_disk) == 2 and all(n.endswith(".png") and "passwd" not in n for n in on_disk)
        assert not (Path(upload_dir).parent / "etc").exists()

    def test_extension_matches_real_type(self, client, cat):
        cid = make(client, cat)
        r = up(client, cid, [f("holiday.mp4", _png())])  # PNG nommé .mp4
        assert r.json()["attachments"][0]["filename"] == "holiday.png"


class TestRights:
    def test_only_owner_can_upload(self, client, cat):
        cid = make(client, cat, "stud")
        assert up(client, cid, [f("a.png", _png())], who="stud2").status_code == 404
        assert up(client, 999999, [f("a.png", _png())]).status_code == 404

    def test_staff_cannot_use_student_route(self, client, cat):
        cid = make(client, cat)
        for who in ("coord", "admin"):
            assert up(client, cid, [f("a.png", _png())], who=who).status_code == 403

    def test_unauthenticated(self, client, cat):
        cid = make(client, cat)
        assert client.post(f"/api/student/complaints/{cid}/attachments", files=[f("a.png", _png())]).status_code == 401
        assert client.get(f"/api/student/complaints/{cid}/attachments/1").status_code == 401

    def test_closed_complaint_rejects_uploads_and_deletes(self, client, cat):
        cid = make(client, cat)
        att_id = up(client, cid, [f("a.png", _png())]).json()["attachments"][0]["id"]
        adm = auth(client, "admin")
        coord_id = client.get("/auth/me", headers=auth(client, "coord")).json()["id"]
        client.patch(f"/api/admin/complaints/{cid}/assign", headers=adm, json={"assigned_to_id": coord_id})
        for s in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
            client.patch(f"/api/admin/complaints/{cid}/status", headers=adm, json={"status": s})
        assert up(client, cid, [f("b.png", _png())]).status_code == 409
        assert client.delete(f"/api/student/complaints/{cid}/attachments/{att_id}", headers=auth(client, "stud")).status_code == 409
        # la lecture reste possible
        assert client.get(f"/api/student/complaints/{cid}/attachments/{att_id}", headers=auth(client, "stud")).status_code == 200


class TestDownload:
    def test_bytes_content_type_and_headers(self, client, cat):
        cid = make(client, cat)
        data = _png(extra=100)
        a = up(client, cid, [f("pic.png", data)]).json()["attachments"][0]
        r = client.get(f"/api/student/complaints/{cid}/attachments/{a['id']}", headers=auth(client, "stud"))
        assert r.status_code == 200 and r.content == data
        assert r.headers["content-type"] == "image/png"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-disposition"].startswith("inline")
        assert a["size"] == len(data)

    def test_other_student_cannot_download(self, client, cat):
        cid = make(client, cat)
        a = up(client, cid, [f("pic.png", _png())]).json()["attachments"][0]
        assert client.get(f"/api/student/complaints/{cid}/attachments/{a['id']}", headers=auth(client, "stud2")).status_code == 404

    def test_attachment_must_belong_to_the_complaint(self, client, cat):
        c1, c2 = make(client, cat), make(client, cat)
        a = up(client, c1, [f("pic.png", _png())]).json()["attachments"][0]
        assert client.get(f"/api/student/complaints/{c2}/attachments/{a['id']}", headers=auth(client, "stud")).status_code == 404
        assert client.get(f"/api/student/complaints/{c1}/attachments/999999", headers=auth(client, "stud")).status_code == 404

    def test_coordinator_and_admin_access(self, client, cat, other_coord):
        cid = make(client, cat)
        a = up(client, cid, [f("pic.png", _png())]).json()["attachments"][0]
        url = lambda role: f"/api/{role}/complaints/{cid}/attachments/{a['id']}"
        adm, coord = auth(client, "admin"), auth(client, "coord")
        assert client.get(url("admin"), headers=adm).status_code == 200
        assert client.get(url("coordinator"), headers=coord).status_code == 404       # pas encore assignée
        coord_id = client.get("/auth/me", headers=coord).json()["id"]
        client.patch(f"/api/admin/complaints/{cid}/assign", headers=adm, json={"assigned_to_id": coord_id})
        assert client.get(url("coordinator"), headers=coord).status_code == 200
        assert client.get(url("coordinator"), headers=auth(client, other_coord)).status_code == 404  # autre coordinateur
        assert client.get(url("admin"), headers=auth(client, "stud")).status_code == 403

    def test_detail_lists_attachments_for_every_role(self, client, cat):
        cid = make(client, cat)
        up(client, cid, [f("pic.png", _png())])
        adm = auth(client, "admin")
        assert len(client.get(f"/api/admin/complaints/{cid}", headers=adm).json()["attachments"]) == 1
        assert len(client.get(f"/api/student/complaints/{cid}", headers=auth(client, "stud")).json()["attachments"]) == 1

    def test_file_missing_on_disk(self, client, cat, upload_dir):
        cid = make(client, cat)
        a = up(client, cid, [f("pic.png", _png())]).json()["attachments"][0]
        for p in (upload_dir / str(cid)).iterdir():
            p.unlink()
        assert client.get(f"/api/student/complaints/{cid}/attachments/{a['id']}", headers=auth(client, "stud")).status_code == 404

    def test_notification_for_assigned_coordinator(self, client, cat):
        cid = make(client, cat)
        coord = auth(client, "coord")
        coord_id = client.get("/auth/me", headers=coord).json()["id"]
        client.patch(f"/api/admin/complaints/{cid}/assign", headers=auth(client, "admin"), json={"assigned_to_id": coord_id})
        up(client, cid, [f("pic.png", _png())])
        msgs = [n["message"] for n in client.get("/api/coordinator/notifications", headers=coord).json()]
        assert any("New attachment" in m for m in msgs)


class TestDelete:
    def test_owner_deletes_and_file_is_removed(self, client, cat, upload_dir):
        cid = make(client, cat)
        files = up(client, cid, [f("a.png", _png()), f("b.png", _png())]).json()["attachments"]
        r = client.delete(f"/api/student/complaints/{cid}/attachments/{files[0]['id']}", headers=auth(client, "stud"))
        assert r.status_code == 200 and [a["id"] for a in r.json()["attachments"]] == [files[1]["id"]]
        assert len(list((upload_dir / str(cid)).iterdir())) == 1
        assert client.get(f"/api/student/complaints/{cid}/attachments/{files[0]['id']}", headers=auth(client, "stud")).status_code == 404

    def test_cannot_delete_others_or_unknown(self, client, cat):
        cid = make(client, cat)
        a = up(client, cid, [f("a.png", _png())]).json()["attachments"][0]
        assert client.delete(f"/api/student/complaints/{cid}/attachments/{a['id']}", headers=auth(client, "stud2")).status_code == 404
        assert client.delete(f"/api/student/complaints/{cid}/attachments/999999", headers=auth(client, "stud")).status_code == 404

    def test_deleting_makes_room_for_new_files(self, client, cat):
        cid = make(client, cat)
        files = up(client, cid, [f(f"{i}.png", _png()) for i in range(5)]).json()["attachments"]
        assert up(client, cid, [f("x.png", _png())]).status_code == 409
        client.delete(f"/api/student/complaints/{cid}/attachments/{files[0]['id']}", headers=auth(client, "stud"))
        assert up(client, cid, [f("x.png", _png())]).status_code == 201

    def test_deleting_a_complaint_cascades_to_attachment_rows(self, client, cat):
        cid = make(client, cat)
        up(client, cid, [f("a.png", _png())])
        with SessionLocal() as db:
            db.delete(db.get(Complaint, cid))
            db.commit()
            assert db.query(Attachment).filter_by(complaint_id=cid).count() == 0
