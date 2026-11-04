"""initial schema (LLD 05 3.3-3.7): tables, indexes, append-only triggers, roles, grants

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None

DDL = r"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE batch (
  id text PRIMARY KEY,
  file_sha256 char(64) NOT NULL,
  idempotency_key text NOT NULL,
  s3_key text NOT NULL,
  source_systems text[] NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('queued','processing','done','ai_partial','empty','failed')),
  ai_status text NOT NULL DEFAULT 'not_started'
    CHECK (ai_status IN ('not_started','running','complete','partial','skipped')),
  record_count integer CHECK (record_count >= 0),
  chunk_count integer CHECK (chunk_count >= 0),
  error_code text,
  error_detail jsonb,
  reference_versions jsonb NOT NULL DEFAULT '{}',
  trace_id text,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE (idempotency_key),
  UNIQUE (file_sha256)  -- PROVISIONAL(OQ-125): blocks explicit re-run of the same file
);
CREATE INDEX batch_created_idx ON batch (created_at DESC);

CREATE TABLE batch_chunk (  -- PROVISIONAL(OQ-126)
  batch_id text NOT NULL REFERENCES batch(id),
  chunk_no integer NOT NULL CHECK (chunk_no >= 1),
  row_from integer NOT NULL,
  row_to integer NOT NULL CHECK (row_to >= row_from),
  status text NOT NULL CHECK (status IN ('queued','running','done','failed')),
  attempts smallint NOT NULL DEFAULT 0,
  lease_expires_at timestamptz,
  error_code text,
  ai_tasks_enqueued integer NOT NULL DEFAULT 0,
  started_at timestamptz,
  finished_at timestamptz,
  PRIMARY KEY (batch_id, chunk_no)
);
CREATE INDEX batch_chunk_status_idx ON batch_chunk (batch_id, status);

CREATE TABLE record_snapshot (
  batch_id text NOT NULL REFERENCES batch(id),
  row_number integer NOT NULL CHECK (row_number >= 1),
  record_key text NOT NULL,
  source_system text,
  item_id text,
  raw jsonb NOT NULL,
  normalised jsonb NOT NULL,
  PRIMARY KEY (batch_id, row_number),
  UNIQUE (batch_id, record_key)
);
CREATE INDEX record_snapshot_dupid_idx ON record_snapshot (batch_id, source_system, item_id);
CREATE INDEX record_snapshot_mpn_idx ON record_snapshot (batch_id, ((normalised->>'mpn_key')))
  WHERE normalised->>'mpn_key' <> '';

CREATE TABLE finding (
  id text PRIMARY KEY,
  batch_id text NOT NULL,
  record_key text NOT NULL,
  item_id text,
  issue_type text NOT NULL CHECK (issue_type IN (
    'malformed_row','incomplete_row','missing_part_number','unsupported_uom',
    'duplicate_item_id','weak_description','possible_duplicate',
    'category_mismatch_candidate','conflicting_source_values','suspicious_content')),
  severity text NOT NULL CHECK (severity IN ('low','medium','high')),
  severity_rank smallint GENERATED ALWAYS AS (
    CASE severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END) STORED,
  confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  explanation text NOT NULL CHECK (length(explanation) > 0),
  evidence jsonb NOT NULL CHECK (evidence <> '{}'::jsonb),
  suggested_action text NOT NULL,
  suggested_value jsonb,
  source text NOT NULL CHECK (source IN ('deterministic_rule','heuristic','ai_suggestion')),
  also_detected_by text[] NOT NULL DEFAULT '{}',
  rule_id text NOT NULL,
  rule_version text NOT NULL,
  model_id text,
  prompt_version text,
  status text NOT NULL DEFAULT 'needs_review' CHECK (status IN (
    'needs_review','approved','rejected','investigating','in_change_file','closed','withdrawn')),
  dedupe_key text NOT NULL UNIQUE,  -- PROVISIONAL(OQ-109): derivation undecided, not necessarily a sha256
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (source <> 'ai_suggestion' OR (model_id IS NOT NULL AND prompt_version IS NOT NULL)),
  FOREIGN KEY (batch_id, record_key) REFERENCES record_snapshot (batch_id, record_key)
);
CREATE INDEX finding_queue_idx ON finding (batch_id, status, severity_rank DESC, confidence DESC, id);
CREATE INDEX finding_type_idx ON finding (batch_id, issue_type);
CREATE INDEX finding_record_idx ON finding (batch_id, record_key);

CREATE TABLE decision (
  id text PRIMARY KEY,
  finding_id text NOT NULL REFERENCES finding(id),
  decision_seq integer NOT NULL CHECK (decision_seq >= 1),
  action text NOT NULL CHECK (action IN ('approve','reject','investigate')),
  reason_code text,
  comment text,
  edited_value jsonb,
  decided_by text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  approval_level smallint NOT NULL DEFAULT 1 CHECK (approval_level IN (1,2)),
  idempotency_key text,
  CHECK (action <> 'reject' OR reason_code IS NOT NULL),
  UNIQUE (finding_id, decision_seq, approval_level),
  UNIQUE (idempotency_key)
);
CREATE INDEX decision_finding_idx ON decision (finding_id);

CREATE TABLE ai_task (
  id text PRIMARY KEY,
  task_key char(64) NOT NULL UNIQUE,
  batch_id text NOT NULL REFERENCES batch(id),
  record_key text NOT NULL,
  counterpart_record_key text,
  task_type text NOT NULL CHECK (task_type IN ('category_check','normalise_description','duplicate_adjudication')),
  model_id text NOT NULL,
  prompt_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('queued','running','succeeded','dropped','failed','skipped')),
  attempts smallint NOT NULL DEFAULT 0,
  tokens_in integer, tokens_out integer, cost_usd numeric(12,6), latency_ms integer,
  error_code text,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ai_task_batch_status_idx ON ai_task (batch_id, status);

CREATE TABLE audit_event (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  seq bigint NOT NULL,
  actor text NOT NULL,
  event_type text NOT NULL,
  entity text NOT NULL,
  payload jsonb NOT NULL,
  prev_hash char(64) NOT NULL,
  hash char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  UNIQUE (seq)
);
CREATE INDEX audit_event_created_idx ON audit_event (created_at);
CREATE INDEX audit_event_entity_idx ON audit_event (entity);

CREATE TABLE reference_data (
  type text NOT NULL,
  version integer NOT NULL CHECK (version >= 1),
  "values" jsonb NOT NULL,
  effective_from timestamptz NOT NULL,
  created_by text NOT NULL,
  PRIMARY KEY (type, version)
);
CREATE INDEX reference_data_active_idx ON reference_data (type, effective_from DESC);

CREATE TABLE item_embedding (
  ref_id text NOT NULL,
  source text NOT NULL CHECK (source IN ('approved','taxonomy')),
  model_id text NOT NULL,
  embedding vector(1024) NOT NULL,  -- PROVISIONAL(OQ-700): dimension follows the embedding model
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, ref_id)
);
CREATE INDEX item_embedding_hnsw_idx ON item_embedding USING hnsw (embedding vector_cosine_ops);

CREATE TABLE export (  -- PROVISIONAL(OQ-126)
  id text PRIMARY KEY,
  batch_id text NOT NULL REFERENCES batch(id),
  status text NOT NULL CHECK (status IN ('queued','running','ready','failed')),
  format text,  -- OQ-134
  s3_key text,
  finding_count integer,
  requested_by text NOT NULL,
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE (idempotency_key)
);

-- Append-only enforcement (defence in depth next to REVOKE below)
CREATE FUNCTION dqa_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (% rejected)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'integrity_constraint_violation';
END $$;
CREATE TRIGGER record_snapshot_append_only BEFORE UPDATE OR DELETE ON record_snapshot
  FOR EACH ROW EXECUTE FUNCTION dqa_reject_mutation();
CREATE TRIGGER decision_append_only BEFORE UPDATE OR DELETE ON decision
  FOR EACH ROW EXECUTE FUNCTION dqa_reject_mutation();
CREATE TRIGGER audit_event_append_only BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION dqa_reject_mutation();
CREATE TRIGGER record_snapshot_no_truncate BEFORE TRUNCATE ON record_snapshot
  FOR EACH STATEMENT EXECUTE FUNCTION dqa_reject_mutation();
CREATE TRIGGER decision_no_truncate BEFORE TRUNCATE ON decision
  FOR EACH STATEMENT EXECUTE FUNCTION dqa_reject_mutation();
CREATE TRIGGER audit_event_no_truncate BEFORE TRUNCATE ON audit_event
  FOR EACH STATEMENT EXECUTE FUNCTION dqa_reject_mutation();

-- Metadata-only view for Platform Admin (LLD 05 3.5)
CREATE VIEW batch_metadata AS SELECT id, status, record_count, created_at FROM batch;

-- Roles (NOLOGIN groups; login roles are granted membership by infra)
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['dqa_api','dqa_worker','dqa_agent','dqa_auditor','dqa_platform_admin'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', r);
    END IF;
  END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON record_snapshot, decision, audit_event FROM PUBLIC;

-- dqa_api
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dqa_api;
REVOKE SELECT ON batch_metadata FROM dqa_api;
GRANT INSERT ON batch, finding, decision, export, audit_event TO dqa_api;
GRANT UPDATE (status, updated_at) ON finding TO dqa_api;
-- dqa_worker  (PROVISIONAL: UPDATE on export for the dqa-export consumer)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dqa_worker;
REVOKE SELECT ON batch_metadata FROM dqa_worker;
GRANT INSERT, UPDATE ON batch, batch_chunk, ai_task, export TO dqa_worker;
GRANT INSERT ON record_snapshot, finding, audit_event TO dqa_worker;
-- dqa_agent  (PROVISIONAL(OQ-212): INSERT on finding stands in for the undefined draft-findings table)
GRANT SELECT ON reference_data, record_snapshot, batch, item_embedding TO dqa_agent;
GRANT INSERT, UPDATE ON ai_task TO dqa_agent;
GRANT SELECT ON ai_task TO dqa_agent;
GRANT INSERT ON finding TO dqa_agent;
-- dqa_auditor
GRANT SELECT ON finding, decision, audit_event TO dqa_auditor;
-- dqa_platform_admin: aggregate metadata only
GRANT SELECT ON batch_metadata TO dqa_platform_admin;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO dqa_api, dqa_worker;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(DDL.replace("%", "%%"))  # psycopg treats % as a placeholder


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations (expand/migrate/contract)")
