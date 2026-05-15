"""Derive supersedes edges between decisions.

A decision D2 supersedes D1 iff all of the following hold:
  1. They share at least one entity (touch the same code area).
  2. D2's valid_from is strictly after D1's.
  3. Their claims are semantically related above a threshold.

Why these three signals, in plain terms: entity overlap proves they're
about the same thing; temporal ordering establishes which is the
successor; semantic similarity rules out two unrelated decisions that
happen to share an entity name. Together they're conservative we'd
rather miss an edge than create a wrong one, because wrong edges
poison the temporal answers downstream.
"""

import sqlite3
import struct
from collections import defaultdict

from rich.console import Console

# Cosine similarity threshold above which we treat two decisions as
# semantically related enough to be candidates for supersession.
# Calibrated low-conservative: we want recall here, the entity-overlap
# filter does the precision work.
SIM_THRESHOLD = 0.55


def _deserialize_vector(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _load_decisions(conn: sqlite3.Connection) -> dict[int, dict]:
    """Load all decisions with their entities and vectors."""
    out: dict[int, dict] = {}
    for row in conn.execute(
        "SELECT id, valid_from, claim FROM decisions"
    ).fetchall():
        out[row[0]] = {
            "id": row[0],
            "valid_from": row[1],
            "claim": row[2],
            "entities": set(),
            "vec": None,
        }

    for decision_id, entity in conn.execute(
        "SELECT decision_id, entity FROM decision_entities"
    ).fetchall():
        if decision_id in out:
            out[decision_id]["entities"].add(entity.lower())

    for decision_id, blob in conn.execute(
        "SELECT decision_id, embedding FROM decision_vec"
    ).fetchall():
        if decision_id in out:
            out[decision_id]["vec"] = _deserialize_vector(blob)

    return out


def derive_supersedes(conn: sqlite3.Connection, console: Console) -> dict[str, int]:
    """Compute supersedes edges and update valid_to on superseded decisions."""
    decisions = _load_decisions(conn)
    if not decisions:
        console.print("[yellow]No decisions to process.[/yellow]")
        return {"edges": 0, "closed": 0}

    # Index decisions by entity for fast candidate lookup.
    by_entity: dict[str, list[int]] = defaultdict(list)
    for d in decisions.values():
        for e in d["entities"]:
            by_entity[e].append(d["id"])

    # Clear prior supersedes edges (they're derived; re-run is authoritative).
    conn.execute("DELETE FROM decision_edges WHERE relation = 'supersedes'")

    edges: list[tuple[int, int]] = []   # (newer_id, older_id) — newer supersedes older
    seen_pairs: set[tuple[int, int]] = set()

    for d in decisions.values():
        if d["vec"] is None or not d["entities"]:
            continue

        # Candidates: other decisions sharing at least one entity.
        candidates: set[int] = set()
        for e in d["entities"]:
            candidates.update(by_entity[e])
        candidates.discard(d["id"])

        for cid in candidates:
            other = decisions[cid]
            if other["vec"] is None:
                continue

            # Order: newer supersedes older. Equal timestamps → skip
            # (can't tell which way the supersession goes).
            if d["valid_from"] <= other["valid_from"]:
                continue

            pair = (d["id"], other["id"])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            sim = _cosine(d["vec"], other["vec"])
            if sim >= SIM_THRESHOLD:
                edges.append(pair)

    # Insert edges.
    for newer, older in edges:
        conn.execute(
            """INSERT OR IGNORE INTO decision_edges
               (src_decision_id, dst_decision_id, relation)
               VALUES (?, ?, 'supersedes')""",
            (newer, older),
        )

    # Close out valid_to on each superseded decision: valid_to becomes
    # the valid_from of its most-recent superseder.
    closed = 0
    for older_id in {older for _new, older in edges}:
        newest_superseder = conn.execute(
            """SELECT MIN(d.valid_from)
               FROM decision_edges e
               JOIN decisions d ON d.id = e.src_decision_id
               WHERE e.dst_decision_id = ? AND e.relation = 'supersedes'""",
            (older_id,),
        ).fetchone()[0]
        if newest_superseder is not None:
            cur = conn.execute(
                "UPDATE decisions SET valid_to = ? WHERE id = ? AND valid_to IS NULL",
                (newest_superseder, older_id),
            )
            if cur.rowcount:
                closed += 1

    conn.commit()
    return {"edges": len(edges), "closed": closed}