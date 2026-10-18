"""Données de démonstration : python -m scripts.seed"""
from sqlalchemy import select

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Category, Department, Role, User


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)):
            print("Base déjà initialisée.")
            return
        dept = Department(name="Scolarité")
        db.add_all([dept, Department(name="Informatique")])
        db.add_all([
            Category(name="Notes et examens", description="Erreur de note, correction..."),
            Category(name="Infrastructures", description="Salles, matériel, wifi..."),
            Category(name="Administration", description="Inscriptions, documents..."),
        ])
        db.flush()
        pwd = hash_password("admin123")
        db.add_all([
            User(username="admin", email="admin@univ.edu", hashed_password=pwd, role=Role.ADMIN, first_name="Ada", last_name="Admin"),
            User(username="coord", email="coord@univ.edu", hashed_password=pwd, role=Role.COORDINATOR, department_id=dept.id, first_name="Carl", last_name="Coord"),
            User(username="student", email="student@univ.edu", hashed_password=pwd, role=Role.STUDENT, student_id="2024-0001", first_name="Sam", last_name="Student"),
        ])
        db.commit()
        print("OKay -> demo accounts create which successfuly (default identifiant : admin / coord / student ; mot de passe : [admin123])")


if __name__ == "__main__":
    main()
