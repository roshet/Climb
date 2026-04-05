import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database import Base, init_db

@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
