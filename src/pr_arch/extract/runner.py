"""Run the extractor over artifacts that haven't been extracted yet."""

import sqlite3
from typing import Any

from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from pr_arch.config import EXTRACTOR_VERSION
from pr_arch.extract.prompts import SYSTEM_PROMPT, user_prompt
from pr_arch.extract.schema import ExtractionResult
from pr_arch.llm.anthropic import AnthropicClient


def _pending_artifacts(conn: sqlite3.Connection, version: str) -> list[dict[str, Any]]:
    """Artifacts that don't yet have decisions at the current extractor version.

    An artifact is 'extracted at v' if there exists at least one decision
    row for it with that extractor_version — OR we've recorded an explicit
    'no decisions found' marker for it (see _mark_processed below).
    """
    rows = conn.execute(
        """
        SELECT a.id, a.number, a.title, a.body, a.merged_at, a.created_at
        FROM artifacts a
        WHERE a.kind = 'pr'
          AND NOT EXISTS (
              SELECT 1 FROM decisions d
              WHERE d.artifact_id = a.id
                AND d.extractor_version = ?
          )
          AND NOT EXISTS (
              SELECT 1 FROM extractor_runs r
              WHERE r.artifact_id = a.id
                AND r.extractor_version = ?
          )
        ORDER BY a.created_at
        """,
        (version, version),
    ).fetchall()
    cols = ["id", "number", "title", "body", "merged_at", "created_at"]
    return [dict(zip(cols, r)) for r in rows]


def _ensure_runs_table(conn: sqlite3.Connection) -> None:
    """Track which artifacts have been processed, including 'no decisions'.

    Without this, an artifact with zero extracted decisions would look
    'pending' forever and be re-extracted every run.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS extractor_runs (
               artifact_id INTEGER NOT NULL REFERENCES artifacts(id),
               extractor_version TEXT NOT NULL,
               decisions_found INTEGER NOT NULL,
               error TEXT,
               PRIMARY KEY (artifact_id, extractor_version)
           )"""
    )


def _record_run(
    conn: sqlite3.Connection,
    artifact_id: int,
    version: str,
    decisions_found: int,
    error: str | None,
) -> None:
    conn.execute(
        """INSERT INTO extractor_runs
           (artifact_id, extractor_version, decisions_found, error)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(artifact_id, extractor_version)
           DO UPDATE SET decisions_found = excluded.decisions_found,
                         error = excluded.error""",
        (artifact_id, version, decisions_found, error),
    )


def _store_decisions(
    conn: sqlite3.Connection,
    artifact_id: int,
    merged_at: str | None,
    created_at: str,
    result: ExtractionResult,
) -> int:
    """Persist extracted decisions. Returns the number written."""
    valid_from = merged_at or created_at
    count = 0
    for d in result.decisions:
        cur = conn.execute(
            """INSERT INTO decisions
               (artifact_id, claim, rationale, confidence, extractor_version,
                valid_from, valid_to)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (artifact_id, d.claim, d.rationale, d.confidence,
             EXTRACTOR_VERSION, valid_from),
        )
        decision_id = cur.lastrowid
        for entity in d.entities:
            conn.execute(
                """INSERT OR IGNORE INTO decision_entities
                   (decision_id, entity) VALUES (?, ?)""",
                (decision_id, entity),
            )
        count += 1
    return count


def extract_pending(
    llm: AnthropicClient,
    conn: sqlite3.Connection,
    console: Console,
    limit: int | None = None,
) -> dict[str, int]:
    """Extract decisions from all artifacts pending at the current version."""
    _ensure_runs_table(conn)
    pending = _pending_artifacts(conn, EXTRACTOR_VERSION)
    if limit:
        pending = pending[:limit]

    if not pending:
        console.print("[green]Nothing to extract.[/green]")
        return {"processed": 0, "decisions": 0, "errors": 0}

    console.print(
        f"  extracting [cyan]{len(pending)}[/cyan] artifact(s) at "
        f"version [cyan]{EXTRACTOR_VERSION}[/cyan]"
    )

    processed = 0
    decisions_total = 0
    errors = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("extracting", total=len(pending))

        for art in pending:
            try:
                raw = llm.complete_json(
                    SYSTEM_PROMPT,
                    user_prompt(art["title"], art["body"] or ""),
                )
                result = ExtractionResult.model_validate(raw)
                n = _store_decisions(
                    conn, art["id"], art["merged_at"], art["created_at"], result
                )
                _record_run(conn, art["id"], EXTRACTOR_VERSION, n, None)
                decisions_total += n
                processed += 1
            except (ValueError, ValidationError) as e:
                _record_run(conn, art["id"], EXTRACTOR_VERSION, 0, str(e)[:500])
                errors += 1

            # Commit per-artifact so a crash mid-run doesn't lose progress.
            conn.commit()
            progress.update(task, advance=1)

    return {"processed": processed, "decisions": decisions_total, "errors": errors}