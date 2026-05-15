"""Per-repo high-water mark for incremental fetches.

Stored in a small key-value table so we don't need a separate state file.
"""

import sqlite3


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create the watermark table if it doesn't exist.

    This is intentionally outside the migration files — it's tiny, has no
    foreign keys, and being able to create it on first use keeps the ingest
    module self-contained.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ingest_watermark (
               repo TEXT PRIMARY KEY,
               last_updated_at TEXT NOT NULL
           )"""
    )


def get(conn: sqlite3.Connection, repo: str) -> str | None:
    ensure_table(conn)
    row = conn.execute(
        "SELECT last_updated_at FROM ingest_watermark WHERE repo = ?", (repo,)
    ).fetchone()
    return row[0] if row else None


def set_(conn: sqlite3.Connection, repo: str, updated_at: str) -> None:
    ensure_table(conn)
    conn.execute(
        """INSERT INTO ingest_watermark (repo, last_updated_at) VALUES (?, ?)
           ON CONFLICT(repo) DO UPDATE SET last_updated_at = excluded.last_updated_at""",
        (repo, updated_at),
    )