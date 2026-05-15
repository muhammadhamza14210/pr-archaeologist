import sqlite3
from typing import Any

# ── Tool schemas (Anthropic tool-definition format) ─────────────────

SEARCH_EPISODIC_SCHEMA = {
    "name": "search_episodic",
    "description": (
        "Full-text search over repository artifacts (pull requests, issues, "
        "commits). Use this for questions about what happened, when something "
        "changed, or who was involved. Returns matching artifacts with their "
        "number, title, author, dates, and a snippet of the body."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search terms. Use the key nouns from the user's question "
                    "(e.g. 'redis sessions', 'ruff linter'). Avoid full "
                    "sentences — FTS5 matches tokens."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return. Default 5.",
            },
        },
        "required": ["query"],
    },
}

TOOL_SCHEMAS = [SEARCH_EPISODIC_SCHEMA]


# ── Tool executors ──────────────────────────────────────────────────

def _fts_query(raw: str) -> str:
    """Turn a free-text query into a safe FTS5 MATCH expression.

    We quote each token and OR them together. Quoting neutralizes FTS5
    operator characters in user/LLM input, so a stray '-' or '*' can't
    blow up the query or change its meaning.
    """
    tokens = [t for t in raw.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def search_episodic(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Execute an FTS5 search over the artifacts table."""
    match = _fts_query(query)
    rows = conn.execute(
        """
        SELECT a.kind, a.number, a.title, a.author, a.created_at,
               a.merged_at, a.state, a.url,
               substr(a.body, 1, 300) AS snippet
        FROM artifacts_fts f
        JOIN artifacts a ON a.id = f.rowid
        WHERE artifacts_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match, limit),
    ).fetchall()

    cols = ["kind", "number", "title", "author", "created_at",
            "merged_at", "state", "url", "snippet"]
    return [dict(zip(cols, row)) for row in rows]


TOOL_EXECUTORS = {
    "search_episodic": search_episodic,
}