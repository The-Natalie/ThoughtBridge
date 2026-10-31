-- ThoughtBridge schema v1. Single-writer SQLite. Idempotent: safe to execute repeatedly.
-- Conventions: TEXT uuid PKs except chunks (INTEGER, rowid-aligned with chunks_vec);
-- timestamps TEXT ISO-8601 UTC; JSON columns TEXT. FK enforcement + vec0 extension
-- loading happen in connection.py (every connection), not here.

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('embedding_model', 'BAAI/bge-small-en-v1.5');
INSERT OR IGNORE INTO meta (key, value) VALUES ('embedding_dim', '384');

-- Layer 1: immutable source artifacts.
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

-- Layer 2: searchable chunks. INTEGER PK shared with chunks_vec rowid by construction.
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
  chunk_idx INTEGER NOT NULL,
  span_start INTEGER NOT NULL,
  span_end INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_artifact ON chunks(artifact_id);

-- Keyword index: external-content FTS5 over chunks(text), kept in sync by triggers.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text,
  content='chunks',
  content_rowid='id',
  tokenize='porter'
);
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;

-- Vector index: vec0 table holding ONLY rowid + embedding. Dim is baked at CREATE
-- time and must match meta.embedding_dim / the configured EMBEDDING_MODEL.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
  embedding float[384]
);

-- Layer 3: extracted facts. fact_chunks join makes F-10 support counting a query.
CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL,
  skills TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0.0,
  model TEXT NOT NULL DEFAULT '',
  prompt_version TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_chunks (
  fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  PRIMARY KEY (fact_id, chunk_id)
);
CREATE INDEX IF NOT EXISTS idx_fact_chunks_chunk ON fact_chunks(chunk_id);
CREATE TABLE IF NOT EXISTS fact_links (
  from_fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  to_fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  PRIMARY KEY (from_fact_id, to_fact_id, relation)
);

-- Layer 4: AI interpretations. Never re-embedded as ground truth.
CREATE TABLE IF NOT EXISTS interpretations (
  id TEXT PRIMARY KEY,
  interp_kind TEXT NOT NULL,
  artifact_id TEXT REFERENCES artifacts(id) ON DELETE CASCADE,
  chunk_ids TEXT NOT NULL DEFAULT '[]',
  fact_ids TEXT NOT NULL DEFAULT '[]',
  content TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interpretations_artifact ON interpretations(artifact_id);

-- Versioned explanations + explicit success markers (PRD F-4).
CREATE TABLE IF NOT EXISTS explanations (
  id TEXT PRIMARY KEY,
  concept TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  steps TEXT NOT NULL DEFAULT '{}',
  mapping TEXT NOT NULL DEFAULT '[]',
  limitations TEXT NOT NULL DEFAULT '',
  reused_from TEXT REFERENCES explanations(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_explanations_concept ON explanations(concept);
CREATE TABLE IF NOT EXISTS explanation_markers (
  id TEXT PRIMARY KEY,
  explanation_id TEXT NOT NULL REFERENCES explanations(id) ON DELETE CASCADE,
  scope TEXT NOT NULL,
  step TEXT,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_markers_explanation ON explanation_markers(explanation_id);

-- Practice attempts (PRD F-7).
CREATE TABLE IF NOT EXISTS attempts (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  question_kind TEXT,
  explanation_id TEXT REFERENCES explanations(id) ON DELETE SET NULL,
  question TEXT NOT NULL,
  answer TEXT,
  feedback TEXT,
  grounding TEXT,
  created_at TEXT NOT NULL
);

-- Conversation memory: append-only turn log with role labels (PRD F-12).
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  mode TEXT,
  citations TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_conversation ON turns(conversation_id);

-- Single-row profiles (PRD F-6, F-13).
CREATE TABLE IF NOT EXISTS career_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  current_role TEXT NOT NULL DEFAULT '',
  past_roles TEXT NOT NULL DEFAULT '[]',
  target_career TEXT NOT NULL DEFAULT '',
  target_position TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS learner_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  emphasis TEXT NOT NULL DEFAULT '{}',
  how_i_learn TEXT NOT NULL DEFAULT ''
);
