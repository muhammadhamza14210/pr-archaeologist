"""Top-level ingestion: fetch PRs, write raw, upsert into artifacts."""

import sqlite3
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from pr_arch.ingest import watermark
from pr_arch.ingest.github import fetch_pulls
from pr_arch.ingest.store import write_raw


def _upsert_artifact(conn: sqlite3.Connection, repo: str, pr: dict[str, Any], h: str) -> bool:
    """Insert or update an artifact row. Returns True if a new row was inserted."""
    state = "merged" if pr.get("merged_at") else pr.get("state", "open")
    body = pr.get("body") or ""

    # Try INSERT; on conflict (same content_hash already stored), do nothing.
    cur = conn.execute(
        """INSERT INTO artifacts
           (content_hash, repo, kind, number, title, body, author,
            created_at, merged_at, state, url)
           VALUES (?, ?, 'pr', ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(content_hash) DO NOTHING""",
        (
            h, repo, pr["number"], pr["title"], body,
            (pr.get("user") or {}).get("login"),
            pr["created_at"], pr.get("merged_at"), state, pr["html_url"],
        ),
    )
    return cur.rowcount > 0


def ingest_repo(
    conn: sqlite3.Connection,
    raw_dir: Path,
    repo: str,
    token: str | None,
    console: Console,
) -> dict[str, int]:
    """Fetch new PRs from `repo` and persist them. Returns counts."""
    since = watermark.get(conn, repo)
    if since:
        console.print(f"  incremental: fetching PRs updated after [cyan]{since}[/cyan]")
    else:
        console.print("  first run: fetching all PRs")

    fetched = 0
    inserted = 0
    newest_updated_at: str | None = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("fetching…", total=None)

        for pr in fetch_pulls(repo, token, since=since):
            fetched += 1
            if newest_updated_at is None:
                # First yielded PR is the newest by updated_at desc.
                newest_updated_at = pr["updated_at"]

            h, _path = write_raw(raw_dir, pr)
            if _upsert_artifact(conn, repo, pr, h):
                inserted += 1

            progress.update(task, description=f"fetched {fetched}, new {inserted}")

    if newest_updated_at:
        watermark.set_(conn, repo, newest_updated_at)

    conn.commit()
    return {"fetched": fetched, "inserted": inserted}