"""SqlRepo logic (pagination, idempotency, audit) on SQLite; Postgres-only DDL is covered by
tests/integration/test_sql_repo.py."""
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from dqa.db.schema import metadata
from dqa.db.sql import SqlRepo
from tests.unit.db.contract import RepoContract


class TestSqliteSqlRepo(RepoContract):
    concurrent = False  # one shared in-memory connection

    def make(self):
        e = sa.create_engine("sqlite://", poolclass=StaticPool,
                             connect_args={"check_same_thread": False})
        sa.event.listen(e, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
        metadata.create_all(e)
        return SqlRepo(e)
