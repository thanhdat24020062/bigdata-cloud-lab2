import duckdb, json, uuid, decimal
import sys
from pathlib import Path
T3 = json.loads(Path("evidence/t3-hashes.json").read_text())
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else T3["run_id"]
envelope = {
    "run_id": RUN_ID,
    "curate_run_id": T3["run_id"],
    "contract_version": "research-telemetry-v1",
    "as_of": "2026-02-09T00:00:00Z",
    "store_id": "bd-g01-objects",
    "input_manifest_sha256": T3["trusted_manifest_sha256"],
    "contract_sha256": T3["contract_sha256"],
    "code_sha256": T3["code_bundle_sha256"],
}
con = duckdb.connect('work.duckdb')

for stmt in Path('typed.sql').read_text().split(';'):
    if stmt.strip(): con.execute(stmt)

sql_text = Path('quality.sql').read_text()
sql_before = sql_text.split("CREATE OR REPLACE VIEW curated")[0]
for stmt in sql_before.split(';'):
    if stmt.strip(): con.execute(stmt)

cursor_metrics = con.execute("SELECT * FROM metrics_before")
cols_m = [c[0] for c in cursor_metrics.description]
metrics = [dict(zip(cols_m, row)) for row in cursor_metrics.fetchall()]

cursor_counts = con.execute("SELECT * FROM intake_counts")
cols_c = [c[0] for c in cursor_counts.description]
counts = dict(zip(cols_c, cursor_counts.fetchone()))

for m in metrics:
    m["run_id"] = RUN_ID
    m["contract_version"] = "research-telemetry-v1"

output = {
    **envelope,
    "checkpoint": "minute-60",
    "raw_inventory": counts,
    "metrics": metrics
}

# Hàm chuyển đổi kiểu Decimal sang Float cho JSON
def custom_serializer(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

Path("quality_before.json").write_text(json.dumps(output, indent=2, default=custom_serializer))
print("==> DA TAO FILE quality_before.json THANH CONG!")
print("\n==> 5 Mau Defect de lam bao cao loi:")
for row in con.execute("SELECT * FROM defect_samples LIMIT 5").fetchall(): print(row)
