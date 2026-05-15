import sqlite3
from pr_arch.config import load_settings, EXTRACTOR_VERSION
from pr_arch.llm.anthropic import AnthropicClient
from pr_arch.extract.runner import _store_decisions, _ensure_runs_table, _record_run
from pr_arch.extract.prompts import SYSTEM_PROMPT, user_prompt
from pr_arch.extract.schema import ExtractionResult
from pydantic import ValidationError
from rich.console import Console

console = Console()
settings = load_settings()
llm = AnthropicClient(settings.anthropic_api_key)
conn = sqlite3.connect(settings.db_path)
conn.row_factory = sqlite3.Row
_ensure_runs_table(conn)

rows = conn.execute("""
    SELECT a.id, a.number, a.title, a.body, a.merged_at, a.created_at
    FROM artifacts a
    WHERE a.kind = 'pr' AND length(a.body) > 200
      AND a.number BETWEEN 1500 AND 2800
      AND NOT EXISTS (
          SELECT 1 FROM extractor_runs r
          WHERE r.artifact_id = a.id AND r.extractor_version = ?
      )
    ORDER BY a.number
    LIMIT 30
""", (EXTRACTOR_VERSION,)).fetchall()

print(f"processing {len(rows)} PRs from the middle of Click's history")
for art in rows:
    try:
        raw = llm.complete_json(SYSTEM_PROMPT, user_prompt(art["title"], art["body"] or ""))
        result = ExtractionResult.model_validate(raw)
        n = _store_decisions(conn, art["id"], art["merged_at"], art["created_at"], result)
        _record_run(conn, art["id"], EXTRACTOR_VERSION, n, None)
        print(f'  PR #{art["number"]}: {n} decision(s) — {art["title"][:60]}')
    except (ValueError, ValidationError) as e:
        _record_run(conn, art["id"], EXTRACTOR_VERSION, 0, str(e)[:200])
        print(f'  PR #{art["number"]}: ERROR — {e}')
    conn.commit()
