from sqlalchemy.orm import DeclarativeBase
from .session import engine
from sqlmodel import Session

class Base(DeclarativeBase):
    pass

def get_session():
    with Session(engine) as session:
        yield session