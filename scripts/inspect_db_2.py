import sqlite3
from pr_arch.config import load_settings
conn = sqlite3.connect(load_settings().db_path)
conn.row_factory = sqlite3.Row
print('=== Multi-decision PRs ===')
for r in conn.execute('''
    SELECT a.number, a.title, d.claim, d.rationale, d.confidence
    FROM decisions d JOIN artifacts a ON a.id = d.artifact_id
    WHERE a.number IN (1535, 1558, 1572, 1589, 1604)
    ORDER BY a.number, d.id
'''):
    print(f'PR #{r["number"]}: {r["title"]}')
    print(f'  claim ({r["confidence"]:.2f}): {r["claim"]}')
    print(f'  rationale: {r["rationale"]}')
    print()