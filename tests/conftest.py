import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"  # avant l'import de l'app

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import Category, Department, Role, User


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        with SessionLocal() as db:
            dept = Department(name="Scolarité")
            db.add_all([dept, Category(name="Notes", description="")])
            db.flush()
            pwd = hash_password("Password123!")
            db.add_all([
                User(username="admin", email="a@x.io", hashed_password=pwd, role=Role.ADMIN),
                User(username="coord", email="c@x.io", hashed_password=pwd, role=Role.COORDINATOR, department_id=dept.id),
                User(username="stud", email="s@x.io", hashed_password=pwd, role=Role.STUDENT, student_id="M1"),
                User(username="stud2", email="s2@x.io", hashed_password=pwd, role=Role.STUDENT, student_id="M2"),
            ])
            db.commit()
        yield c


def auth(client, username):
    r = client.post("/auth/login", data={"username": username, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
