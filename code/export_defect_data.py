import duckdb, json
from pathlib import Path

c = duckdb.connect('work.duckdb', read_only=True)
Q = "read_csv('candidate/quarantine.csv', all_varchar=true)"
D = "read_csv('candidate/duplicates.csv', all_varchar=true)"
out = {}
out['n_curated'] = c.execute("SELECT count(*) FROM read_parquet('candidate/curated.parquet')").fetchone()[0]
out['n_quarantine'] = c.execute(f"SELECT count(*) FROM {Q}").fetchone()[0]
out['n_duplicates'] = c.execute(f"SELECT count(*) FROM {D}").fetchone()[0]
out['category_counts'] = dict(c.execute("SELECT category, count(*) FROM defect_samples GROUP BY 1").fetchall())
samples = {}
for cat in out['category_counts']:
    rows = c.execute("SELECT regexp_extract(source_object,'[^/]+$'), source_row FROM defect_samples WHERE category=? ORDER BY 1,2", [cat]).fetchall()
    picked = []
    for obj in sorted({r[0] for r in rows}):
        picked += [f"{o}#{r}" for o, r in rows if o == obj][:3]
    samples[cat] = picked
out['samples'] = samples
out['quarantine_by_reason'] = [list(r) for r in c.execute(f"SELECT stage, primary_reason, count(*) FROM {Q} GROUP BY 1,2 ORDER BY 3 DESC").fetchall()]
out['quarantine_reason_combos'] = [list(r) for r in c.execute(f"SELECT all_reasons, count(*) FROM {Q} GROUP BY 1 ORDER BY 2 DESC LIMIT 20").fetchall()]
out['duplicates_by_reason'] = [list(r) for r in c.execute(f"SELECT reason, count(*) FROM {D} GROUP BY 1").fetchall()]
Path('evidence').mkdir(exist_ok=True)
Path('evidence/defect_data.json').write_text(json.dumps(out, indent=2, default=str))
print(json.dumps(out, indent=2, default=str))
