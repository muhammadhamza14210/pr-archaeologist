import sqlite3
from pathlib import Path
import sqlite_vec


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)

    # Pragmas: WAL for better concurrent reads, foreign keys on because
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Load the vector extension, then immediately disable loading again.
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    return conn


def vec_version(conn: sqlite3.Connection) -> str:
    (version,) = conn.execute("SELECT vec_version()").fetchone()
    return version