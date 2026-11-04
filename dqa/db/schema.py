"""SQLAlchemy Core mirror of the schema created by migrations/versions/0001_initial.py (LLD 05 3.3).

The migration is authoritative for constraints, triggers, grants and pgvector; these Table objects
carry only what SqlRepo queries. JSON/ARRAY use portable variants so the contract suite also runs
on SQLite.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
TEXT_ARRAY = sa.JSON().with_variant(sa.ARRAY(sa.Text()), "postgresql")
TS = sa.DateTime(timezone=True)
metadata = sa.MetaData()

batch = sa.Table(
    "batch", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("file_sha256", sa.String(64), nullable=False, unique=True),
    sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
    sa.Column("s3_key", sa.Text, nullable=False),
    sa.Column("source_systems", TEXT_ARRAY, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("ai_status", sa.Text, nullable=False, server_default="not_started"),
    sa.Column("record_count", sa.Integer), sa.Column("chunk_count", sa.Integer),
    sa.Column("error_code", sa.Text), sa.Column("error_detail", JSON),
    sa.Column("reference_versions", JSON, nullable=False, server_default="{}"),
    sa.Column("trace_id", sa.Text),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_at", TS, nullable=False),
    sa.Column("updated_at", TS, nullable=False),
    sa.Column("completed_at", TS),
)

batch_chunk = sa.Table(
    "batch_chunk", metadata,
    sa.Column("batch_id", sa.Text, sa.ForeignKey("batch.id"), primary_key=True),
    sa.Column("chunk_no", sa.Integer, primary_key=True),
    sa.Column("row_from", sa.Integer, nullable=False), sa.Column("row_to", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
    sa.Column("lease_expires_at", TS), sa.Column("error_code", sa.Text),
    sa.Column("ai_tasks_enqueued", sa.Integer, nullable=False, server_default="0"),
    sa.Column("started_at", TS), sa.Column("finished_at", TS),
)

record_snapshot = sa.Table(
    "record_snapshot", metadata,
    sa.Column("batch_id", sa.Text, sa.ForeignKey("batch.id"), primary_key=True),
    sa.Column("row_number", sa.Integer, primary_key=True),
    sa.Column("record_key", sa.Text, nullable=False),
    sa.Column("source_system", sa.Text), sa.Column("item_id", sa.Text),
    sa.Column("raw", JSON, nullable=False), sa.Column("normalised", JSON, nullable=False),
    sa.UniqueConstraint("batch_id", "record_key"),
)

_RANK = "CASE severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END"
finding = sa.Table(
    "finding", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("batch_id", sa.Text, nullable=False), sa.Column("record_key", sa.Text, nullable=False),
    sa.Column("item_id", sa.Text), sa.Column("issue_type", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("severity_rank", sa.SmallInteger, sa.Computed(_RANK, persisted=True)),
    sa.Column("confidence", sa.Numeric(4, 3, asdecimal=False), nullable=False),
    sa.Column("explanation", sa.Text, nullable=False), sa.Column("evidence", JSON, nullable=False),
    sa.Column("suggested_action", sa.Text, nullable=False), sa.Column("suggested_value", JSON),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("also_detected_by", TEXT_ARRAY, nullable=False),
    sa.Column("rule_id", sa.Text, nullable=False), sa.Column("rule_version", sa.Text, nullable=False),
    sa.Column("model_id", sa.Text), sa.Column("prompt_version", sa.Text),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("dedupe_key", sa.Text, nullable=False, unique=True),
    sa.Column("created_at", TS, nullable=False), sa.Column("updated_at", TS, nullable=False),
    sa.ForeignKeyConstraint(["batch_id", "record_key"],
                            ["record_snapshot.batch_id", "record_snapshot.record_key"]),
)

audit_event = sa.Table(
    "audit_event", metadata,
    sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True,
              autoincrement=True),
    sa.Column("seq", sa.BigInteger, nullable=False, unique=True),
    sa.Column("actor", sa.Text, nullable=False), sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("entity", sa.Text, nullable=False), sa.Column("payload", JSON, nullable=False),
    sa.Column("prev_hash", sa.String(64), nullable=False), sa.Column("hash", sa.String(64), nullable=False),
    sa.Column("created_at", TS, nullable=False),
)
# decision, ai_task, reference_data, export, item_embedding exist only in the migration until
# their modules (11, 08, 10) add repo methods.
