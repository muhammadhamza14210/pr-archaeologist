import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Embedding dimension for text-embedding-3-small. 
EMBED_DIM = 1536


def _current_version(conn: sqlite3.Connection) -> int:
    """Highest applied migration version, or 0 if the table doesn't exist yet."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    except sqlite3.OperationalError:
        return 0
    return row[0] or 0


def _migration_files() -> list[tuple[int, Path]]:
    """All migration files, sorted by their numeric prefix."""
    files = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        version = int(path.stem.split("_")[0])
        files.append((version, path))
    return sorted(files)


def _create_vec_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS decision_vec USING vec0(
            decision_id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBED_DIM}]
        )
        """
    )


def migrate(conn: sqlite3.Connection) -> int:
    current = _current_version(conn)
    applied = 0

    for version, path in _migration_files():
        if version <= current:
            continue
        sql = path.read_text()
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        applied += 1

    _create_vec_table(conn)
    conn.commit()
    return applied