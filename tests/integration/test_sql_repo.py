"""Runs the shared Repo contract and DDL checks against real PostgreSQL 16 + pgvector.

Needs DQA_TEST_DATABASE_URL (e.g. postgresql+psycopg://dqa:dqa@localhost:55432/dqa_test).
The schema is rebuilt with `alembic upgrade head` once per session.
"""
import os
import subprocess
import sys

import pytest
import sqlalchemy as sa

from dqa.db.sql import SqlRepo
from tests.unit.db.contract import RepoContract

URL = os.environ.get("DQA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DQA_TEST_DATABASE_URL not set")

TABLES = ["audit_event", "export", "ai_task", "decision", "finding", "record_snapshot",
          "batch_chunk", "batch"]


@pytest.fixture(scope="module")
def engine():
    admin = sa.create_engine(URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(sa.text("DROP SCHEMA public CASCADE"))
        c.execute(sa.text("CREATE SCHEMA public"))
        c.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    env = {**os.environ, "DQA_DATABASE_URL": URL}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    admin.dispose()
    root = sa.create_engine(URL)  # normal transactions: the repo's unit-of-work semantics matter
    yield root
    root.dispose()


@pytest.fixture
def clean(engine):
    guarded = ("record_snapshot", "decision", "audit_event")
    with engine.begin() as c:  # transactional DDL: triggers are off only inside this transaction
        for t in guarded:
            c.execute(sa.text(f"ALTER TABLE {t} DISABLE TRIGGER USER"))
        for t in TABLES:
            c.execute(sa.text(f"DELETE FROM {t}"))
        for t in guarded:
            c.execute(sa.text(f"ALTER TABLE {t} ENABLE TRIGGER USER"))
    return engine


class TestPostgresSqlRepo(RepoContract):
    @pytest.fixture(autouse=True)
    def _db(self, clean):
        self.engine = clean

    def make(self):
        return SqlRepo(self.engine)

    # Postgres-only guarantees ------------------------------------------------
    def test_pgvector_and_tables_present(self):
        with self.engine.connect() as c:
            assert c.execute(sa.text(
                "SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar() == 1
            n = c.execute(sa.text("SELECT count(*) FROM information_schema.tables WHERE "
                                  "table_schema='public' AND table_name = ANY(:t)"),
                          {"t": ["batch", "batch_chunk", "record_snapshot", "finding", "decision",
                                 "ai_task", "audit_event", "reference_data", "item_embedding",
                                 "export"]}).scalar()
            assert n == 10

    def test_append_only_triggers_block_update_and_delete(self):
        repo = self.seeded(1)
        repo.append_audit(actor="u", event_type="t", entity="e", payload={"a": 1})
        for stmt in ("UPDATE record_snapshot SET item_id='x'", "DELETE FROM record_snapshot",
                     "UPDATE audit_event SET actor='x'", "DELETE FROM audit_event",
                     "TRUNCATE audit_event"):
            with pytest.raises(sa.exc.DBAPIError, match="append-only"), self.engine.begin() as c:
                c.execute(sa.text(stmt))

    def test_check_constraints_reject_bad_rows(self):
        repo = self.seeded(1)
        base = ("INSERT INTO finding (id,batch_id,record_key,issue_type,severity,confidence,"
                "explanation,evidence,suggested_action,source,rule_id,rule_version,dedupe_key,"
                "model_id,prompt_version) VALUES ('f_x','b_1','ERP-A:1','weak_description',"
                "'low',0.5,'e',{ev},'a',{src},'r','1',repeat('z',64),NULL,NULL)")
        for ev, src in (("'{}'::jsonb", "'heuristic'"),  # empty evidence
                        ("'{\"a\":1}'::jsonb", "'ai_suggestion'")):  # AI without model/prompt
            with pytest.raises(sa.exc.IntegrityError), self.engine.begin() as c:
                c.exec_driver_sql(base.format(ev=ev, src=src).replace("%", "%%"))
        assert repo.get_finding("f_x") is None

    def test_role_grants_least_privilege(self):
        def can(role: str, priv: str, obj: str) -> bool:
            with self.engine.connect() as c:
                return bool(c.execute(sa.text(f"SELECT has_table_privilege('{role}', '{obj}', "
                                              f"'{priv}')")).scalar())
        for role in ("dqa_api", "dqa_worker", "dqa_agent", "dqa_auditor", "dqa_platform_admin"):
            for t in ("record_snapshot", "decision", "audit_event"):
                assert not can(role, "UPDATE", t) and not can(role, "DELETE", t), (role, t)
            assert not can(role, "DELETE", "finding") and not can(role, "TRUNCATE", "finding")
        assert can("dqa_worker", "INSERT", "record_snapshot")
        assert not can("dqa_api", "INSERT", "record_snapshot")
        assert can("dqa_api", "INSERT", "decision") and not can("dqa_auditor", "INSERT", "decision")
        assert can("dqa_auditor", "SELECT", "audit_event")
        assert not can("dqa_auditor", "SELECT", "record_snapshot")
        assert can("dqa_platform_admin", "SELECT", "batch_metadata")
        assert not can("dqa_platform_admin", "SELECT", "batch")
        assert not can("dqa_agent", "INSERT", "decision")
