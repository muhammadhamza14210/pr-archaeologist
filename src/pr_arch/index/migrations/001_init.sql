-- Migration 001: initial schema.
-- Three memory layers (episodic / semantic / procedural) plus support tables.

-- ── Migration tracking ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL          -- ISO 8601 timestamp
);

-- ── Episodic layer: raw artifacts ───────────────────────────────────
-- One row per PR, issue, or commit pulled from GitHub.
CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY,
    content_hash  TEXT NOT NULL UNIQUE,   -- hash of raw JSON; dedup + cache key
    repo          TEXT NOT NULL,          -- "owner/name"
    kind          TEXT NOT NULL,          -- 'pr' | 'issue' | 'commit'
    number        INTEGER,                -- PR/issue number; NULL for commits
    title         TEXT NOT NULL,
    body          TEXT,                   -- description / commit message
    author        TEXT,
    created_at    TEXT NOT NULL,          -- ISO 8601, from GitHub
    merged_at     TEXT,                   -- ISO 8601 or NULL
    state         TEXT,                   -- 'merged' | 'closed' | 'open' | 'reverted'
    url           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_repo    ON artifacts(repo);
CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at);

-- Full-text search over artifacts powers "when did we" / "who pushed for" queries.
-- Index title + body; content='artifacts' keeps it in sync with the base table.
CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts USING fts5(
    title,
    body,
    content='artifacts',
    content_rowid='id'
);

-- Triggers to keep the FTS index synced with the artifacts table.
CREATE TRIGGER IF NOT EXISTS artifacts_ai AFTER INSERT ON artifacts BEGIN
    INSERT INTO artifacts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS artifacts_ad AFTER DELETE ON artifacts BEGIN
    INSERT INTO artifacts_fts(artifacts_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS artifacts_au AFTER UPDATE ON artifacts BEGIN
    INSERT INTO artifacts_fts(artifacts_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO artifacts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

-- ── Semantic layer: extracted decision records ──────────────────────
-- One row per decision the extractor pulled out of an artifact.
CREATE TABLE IF NOT EXISTS decisions (
    id                 INTEGER PRIMARY KEY,
    artifact_id        INTEGER NOT NULL REFERENCES artifacts(id),
    claim              TEXT NOT NULL,        -- "chose X over Y because Z"
    rationale          TEXT,                 -- fuller reasoning if present
    confidence         REAL NOT NULL,        -- extractor's self-reported 0.0-1.0
    extractor_version  TEXT NOT NULL,        -- which extractor produced this
    -- Temporal validity. valid_from is when the decision took effect
    -- (usually the artifact's merged_at). valid_to is set when a later
    -- decision supersedes this one; NULL means "still current".
    valid_from         TEXT NOT NULL,        -- ISO 8601
    valid_to           TEXT                  -- ISO 8601 or NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_artifact   ON decisions(artifact_id);
CREATE INDEX IF NOT EXISTS idx_decisions_valid_from ON decisions(valid_from);
CREATE INDEX IF NOT EXISTS idx_decisions_valid_to   ON decisions(valid_to);

-- Entities a decision touches (files, modules, libraries, concepts).
-- Separate table because it's many-per-decision and we may want to
-- query "all decisions touching the auth module".
CREATE TABLE IF NOT EXISTS decision_entities (
    decision_id  INTEGER NOT NULL REFERENCES decisions(id),
    entity       TEXT NOT NULL,
    PRIMARY KEY (decision_id, entity)
);

CREATE INDEX IF NOT EXISTS idx_decision_entities_entity ON decision_entities(entity);

-- ── Procedural layer: the decision graph ────────────────────────────
-- Directed edges between decisions. 'supersedes' is the important one —
-- it's what temporal "as-of" queries traverse.
CREATE TABLE IF NOT EXISTS decision_edges (
    src_decision_id  INTEGER NOT NULL REFERENCES decisions(id),
    dst_decision_id  INTEGER NOT NULL REFERENCES decisions(id),
    relation         TEXT NOT NULL,   -- 'supersedes' | 'relates_to'
    PRIMARY KEY (src_decision_id, dst_decision_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON decision_edges(src_decision_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON decision_edges(dst_decision_id);