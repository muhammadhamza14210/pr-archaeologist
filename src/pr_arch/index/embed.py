"""Embed extracted decisions into the sqlite-vec table."""
import sqlite3
import struct

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from pr_arch.llm.openai import OpenAIEmbeddingClient

BATCH_SIZE = 64 


def _serialize_vector(vec: list[float]) -> bytes:
    """sqlite-vec stores FLOAT[N] as packed little-endian float32 bytes."""
    return struct.pack(f"{len(vec)}f", *vec)


def _decisions_needing_embedding(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Return (decision_id, text_to_embed) for decisions without a vec row."""
    rows = conn.execute(
        """
        SELECT d.id,
               d.claim ||
               CASE WHEN d.rationale IS NOT NULL
                    THEN ' — ' || d.rationale
                    ELSE '' END
               AS embed_text
        FROM decisions d
        WHERE NOT EXISTS (
            SELECT 1 FROM decision_vec v WHERE v.decision_id = d.id
        )
        """
    ).fetchall()
    return rows


def embed_pending(
    client: OpenAIEmbeddingClient,
    conn: sqlite3.Connection,
    console: Console,
) -> int:
    """Embed all decisions that don't yet have an embedding. Returns count."""
    pending = _decisions_needing_embedding(conn)
    if not pending:
        console.print("[green]All decisions already embedded.[/green]")
        return 0

    console.print(f"  embedding [cyan]{len(pending)}[/cyan] decision(s)")

    embedded = 0
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("embedding", total=len(pending))

        for start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[start : start + BATCH_SIZE]
            texts = [text for _id, text in chunk]
            vectors = client.embed(texts)

            for (decision_id, _text), vec in zip(chunk, vectors):
                conn.execute(
                    "INSERT INTO decision_vec (decision_id, embedding) VALUES (?, ?)",
                    (decision_id, _serialize_vector(vec)),
                )
                embedded += 1

            conn.commit()
            progress.update(task, advance=len(chunk))

    return embedded