from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentAdmin
from app.models import Category, Department
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.department import DepartmentCreate, DepartmentOut

departments = APIRouter(prefix="/departments", tags=["Departments"])
categories = APIRouter(prefix="/categories", tags=["Categories"])

_ALLOWED_CATEGORY_UPDATE_FIELDS = frozenset({"name", "description", "is_active"})


def _save(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ce nom existe déjà")


@departments.post("", response_model=DepartmentOut, status_code=201, summary="Créer un département")
def create_department(data: DepartmentCreate, db: DB, _: CurrentAdmin):
    obj = Department(name=data.name)
    db.add(obj)
    _save(db)
    return obj


@departments.get("", response_model=list[DepartmentOut], summary="Lister les départements")
def list_departments(db: DB, _: CurrentAdmin):
    return db.scalars(select(Department).order_by(Department.name)).all()


@departments.patch("/{department_id}", response_model=DepartmentOut, summary="Renommer un département")
def rename_department(department_id: int, data: DepartmentCreate, db: DB, _: CurrentAdmin):
    obj = db.get(Department, department_id)
    if not obj:
        raise HTTPException(404, "Département introuvable")
    obj.name = data.name
    _save(db)
    return obj


@categories.post("", response_model=CategoryOut, status_code=201, summary="Créer une catégorie")
def create_category(data: CategoryCreate, db: DB, _: CurrentAdmin):
    obj = Category(**data.model_dump())
    db.add(obj)
    _save(db)
    return obj


@categories.get("", response_model=list[CategoryOut], summary="Lister toutes les catégories (actives ou non)")
def list_categories(db: DB, _: CurrentAdmin):
    return db.scalars(select(Category).order_by(Category.name)).all()


@categories.patch("/{category_id}", response_model=CategoryOut, summary="Modifier / désactiver une catégorie")
def update_category(category_id: int, data: CategoryUpdate, db: DB, _: CurrentAdmin):
    obj = db.get(Category, category_id)
    if not obj:
        raise HTTPException(404, "Catégorie introuvable")
    for field, value in data.model_dump(exclude_unset=True).items():
        # Ensure field is in the explicit whitelist
        if field not in _ALLOWED_CATEGORY_UPDATE_FIELDS:
            raise HTTPException(400, f"Champ non autorisé: {field}")
        # Disallow private/dunder attributes and require the attribute to exist on the model
        if not field.isidentifier() or field.startswith("_") or not hasattr(obj, field):
            raise HTTPException(400, f"Champ invalide: {field}")
        setattr(obj, field, value)
    _save(db)
    return obj
