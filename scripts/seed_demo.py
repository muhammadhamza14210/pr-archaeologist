from pr_arch.config import load_settings
from pr_arch.db.connection import connect

# (kind, number, title, body, author, created_at, merged_at, state, url)
FAKE_ARTIFACTS = [
    (
        "pr", 402, "Initial auth + Redis sessions",
        "Adds authentication. Sessions stored in Redis for fast TTL-based "
        "expiry and to keep session reads off the primary database.",
        "alice", "2023-06-10", "2023-06-18", "merged",
        "https://github.com/example/repo/pull/402",
    ),
    (
        "pr", 1041, "Stateless sessions via signed cookies",
        "Experiment: move sessions to signed cookies, drop Redis. Reverted "
        "shortly after — broke server-side session invalidation on logout.",
        "bob", "2023-12-02", "2023-12-05", "reverted",
        "https://github.com/example/repo/pull/1041",
    ),
    (
        "pr", 1198, "Move sessions to Postgres",
        "Moves session storage from Redis to Postgres. We already run "
        "Postgres with managed backups and failover; keeping Redis only "
        "for sessions meant a second stateful service to monitor and page "
        "on. Session volume is low enough that Postgres handles it without "
        "measurable latency cost.",
        "alice", "2024-03-01", "2024-03-12", "merged",
        "https://github.com/example/repo/pull/1198",
    ),
    (
        "pr", 1123, "Adopt ruff, drop flake8/isort",
        "Replaces flake8 + isort + pyupgrade with ruff. ~10x faster lint in "
        "CI and collapses three tool configs into one.",
        "dana", "2024-02-10", "2024-02-20", "merged",
        "https://github.com/example/repo/pull/1123",
    ),
]

# (artifact_number, claim, rationale, confidence, valid_from, valid_to)
FAKE_DECISIONS = [
    (
        402, "Chose Redis for session storage over the primary database",
        "Fast TTL-based expiry; keeps session reads off the primary DB.",
        0.9, "2023-06-18", "2024-03-12",  # superseded by #1198
    ),
    (
        1041, "Attempted stateless signed-cookie sessions, then reverted",
        "Broke server-side session invalidation on logout.",
        0.85, "2023-12-05", "2023-12-05",  # reverted same day it landed
    ),
    (
        1198, "Chose Postgres for session storage over Redis",
        "Avoids running Redis as a second stateful service; Postgres "
        "already has managed backups and failover; session volume is low.",
        0.95, "2024-03-12", None,  # current
    ),
    (
        1123, "Chose ruff over flake8 + isort + pyupgrade for linting",
        "~10x faster CI lint; one config instead of three.",
        0.9, "2024-02-20", None,  # current
    ),
]

# (src_artifact_number, dst_artifact_number, relation)
FAKE_EDGES = [
    (1198, 402, "supersedes"),
    (1198, 1041, "relates_to"),
]


def main() -> None:
    settings = load_settings()
    conn = connect(settings.db_path)

    art_id_by_number: dict[int, int] = {}
    for kind, number, title, body, author, created, merged, state, url in FAKE_ARTIFACTS:
        cur = conn.execute(
            """INSERT INTO artifacts
               (content_hash, repo, kind, number, title, body, author,
                created_at, merged_at, state, url)
               VALUES (?, 'example/repo', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"fake-{number}", kind, number, title, body, author,
             created, merged, state, url),
        )
        art_id_by_number[number] = cur.lastrowid

    dec_id_by_number: dict[int, int] = {}
    for number, claim, rationale, conf, vfrom, vto in FAKE_DECISIONS:
        cur = conn.execute(
            """INSERT INTO decisions
               (artifact_id, claim, rationale, confidence, extractor_version,
                valid_from, valid_to)
               VALUES (?, ?, ?, ?, 'fake-v0', ?, ?)""",
            (art_id_by_number[number], claim, rationale, conf, vfrom, vto),
        )
        dec_id_by_number[number] = cur.lastrowid

    for src_num, dst_num, relation in FAKE_EDGES:
        conn.execute(
            """INSERT INTO decision_edges
               (src_decision_id, dst_decision_id, relation) VALUES (?, ?, ?)""",
            (dec_id_by_number[src_num], dec_id_by_number[dst_num], relation),
        )

    conn.commit()
    conn.close()
    print(f"Seeded {len(FAKE_ARTIFACTS)} artifacts, {len(FAKE_DECISIONS)} decisions, "
          f"{len(FAKE_EDGES)} edges.")


if __name__ == "__main__":
    main()