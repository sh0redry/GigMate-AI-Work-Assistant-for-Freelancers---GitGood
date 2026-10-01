import os
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from gigmate.api import app, database
from gigmate.db import Base, make_engine
from gigmate.seed import seed


@pytest.fixture
def environment(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    base_engine = make_engine(url)
    schema = "test_gigmate_" + uuid4().hex
    postgres = url.startswith("postgresql")
    if postgres:
        assert re.fullmatch(r"test_gigmate_[a-f0-9]{32}", schema)
        with base_engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = base_engine.execution_options(schema_translate_map={None: schema})
    else:
        engine = base_engine
    factory = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    seed(factory)

    def override_db():
        with factory.begin() as db:
            yield db

    app.dependency_overrides[database] = override_db
    with TestClient(app) as client:
        yield client, factory, engine
    app.dependency_overrides.clear()
    if postgres:
        with base_engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    base_engine.dispose()


@pytest.fixture
def signed_in(environment):
    client, factory, engine = environment
    response = client.post(
        "/api/v1/auth/login", json={"username": "merchant", "password": "demo-only-change-me"}
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["data"]["csrf_token"]
    return client, factory, engine, {"X-CSRF-Token": csrf}
