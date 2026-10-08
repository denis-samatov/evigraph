"""Test harness: a throw-away database on the local PostgreSQL cluster, migrated by Alembic.

Start the cluster first: `scripts/dev_db.sh start`. EVIGRAPH_TEST_ADMIN_URL overrides the
server used to create the test database.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from evigraph_core.models import Base
from evigraph_core.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get(
    "EVIGRAPH_TEST_ADMIN_URL", "postgresql+psycopg://evigraph@127.0.0.1:54329/evigraph"
)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    name = f"evigraph_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()
    command.upgrade(cfg, "head")
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine(database_url), expire_on_commit=False)


@pytest.fixture(autouse=True)
def _clean(factory: sessionmaker[Session]) -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with factory() as s:
        s.execute(text(f"TRUNCATE {tables} CASCADE"))
        s.commit()


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(database_url=database_url, artifact_dir=tmp_path / "artifacts")
