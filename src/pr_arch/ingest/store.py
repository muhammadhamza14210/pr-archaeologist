"""Content-addressed raw artifact storage.

Each fetched GitHub object is serialized to canonical JSON, hashed, and
written to <raw_dir>/<hash>.json. The hash is the artifact's identity:
identical content → identical path → no duplicate writes.

This store is the input to the extractor. Keeping the raw
JSON on disk (rather than only in the DB) means the extractor can be
re-run with an improved prompt without re-fetching from GitHub.
"""

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical_json(obj: Any) -> bytes:
    """Stable serialization so identical content always hashes the same."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(obj: Any) -> str:
    """Hash a JSON-serializable object. Returns hex sha256."""
    return hashlib.sha256(_canonical_json(obj)).hexdigest()


def write_raw(raw_dir: Path, obj: Any) -> tuple[str, Path]:
    """Write an object to the content-addressed store. Idempotent.

    Returns (hash, path). If a file at the hashed path already exists,
    we don't rewrite it.
    """
    h = content_hash(obj)
    path = raw_dir / h[:2] / f"{h}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canonical_json(obj))
    return h, path