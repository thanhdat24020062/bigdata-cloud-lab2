import duckdb, json, uuid, decimal
import sys
import hashlib
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

print("1. Dang doc cac file output cua Role C...")
con.execute("""
CREATE OR REPLACE VIEW curated AS SELECT * FROM read_parquet('candidate/curated.parquet');
CREATE OR REPLACE VIEW quarantine AS SELECT source_object, try_cast(source_row AS BIGINT) AS source_row FROM read_csv('candidate/quarantine.csv', all_varchar=true);
CREATE OR REPLACE VIEW duplicates AS SELECT source_object, try_cast(source_row AS BIGINT) AS source_row FROM read_csv('candidate/duplicates.csv', all_varchar=true);
""")

print("2. Dang do luong Quality AFTER...")
con.execute("""
CREATE OR REPLACE VIEW ref_match AS SELECT c.record_id, c.temperature_c, q.reference_c, abs(c.temperature_c - q.reference_c) <= (SELECT tol FROM params) AS agrees FROM curated c JOIN qa_reference q USING (record_id);
CREATE OR REPLACE VIEW metrics_after_raw AS SELECT 'Q_REQUIRED' AS rule_id, 'curated candidate' AS cohort, count(*) FILTER (WHERE record_id IS NOT NULL AND sensor_id IS NOT NULL AND event_time_utc IS NOT NULL AND ingest_time_utc IS NOT NULL AND temperature_c IS NOT NULL) AS numerator, count(*) AS denominator, 1.0 AS threshold, 'BLOCK' AS severity FROM curated UNION ALL SELECT 'Q_UNIQUE', 'curated candidate (distinct record_id / rows)', count(DISTINCT record_id), count(*), 1.0, 'BLOCK' FROM curated UNION ALL SELECT 'Q_VALUE', 'curated candidate', count(*) FILTER (WHERE temperature_c BETWEEN (SELECT tmin FROM params) AND (SELECT tmax FROM params)), count(*), 1.0, 'BLOCK' FROM curated UNION ALL SELECT 'Q_REFINT', 'curated candidate', count(*) FILTER (WHERE sensor_id IN (SELECT sensor_id FROM registry_n)), count(*), 1.0, 'BLOCK' FROM curated UNION ALL SELECT 'Q_TIME', 'curated candidate', count(*) FILTER (WHERE event_time_utc <= ingest_time_utc AND ingest_time_utc <= (SELECT as_of FROM params)), count(*), 1.0, 'BLOCK' FROM curated UNION ALL SELECT 'Q_TIMELY', 'curated rows với event<=ingest<=AS_OF', count(*) FILTER (WHERE event_time_utc <= ingest_time_utc AND ingest_time_utc <= (SELECT as_of FROM params) AND epoch(ingest_time_utc) - epoch(event_time_utc) <= (SELECT late_s FROM params)), count(*) FILTER (WHERE event_time_utc <= ingest_time_utc AND ingest_time_utc <= (SELECT as_of FROM params)), 0.95, 'BLOCK' FROM curated UNION ALL SELECT 'Q_REF_AGREE', 'matched reference IDs', count(*) FILTER (WHERE agrees), count(*), 0.95, 'BLOCK' FROM ref_match UNION ALL SELECT 'Q_REF_COVERAGE', 'all 100 reference IDs', (SELECT count(*) FROM ref_match), (SELECT count(*) FROM qa_reference), 1.0, 'BLOCK';
CREATE OR REPLACE VIEW metrics_after AS SELECT rule_id, 'curated-candidate' AS dataset_id, cohort, numerator, denominator, CASE WHEN denominator = 0 THEN NULL ELSE round(cast(numerator AS DOUBLE) / denominator, 4) END AS value, threshold, severity, CASE WHEN denominator = 0 THEN 'NOT_EVALUATED' ELSE 'EVALUATED' END AS status FROM metrics_after_raw;
CREATE OR REPLACE VIEW all_out AS SELECT 'curated' AS src, source_object, source_row FROM curated UNION ALL SELECT 'quarantine', source_object, source_row FROM quarantine UNION ALL SELECT 'duplicates', source_object, source_row FROM duplicates;
CREATE OR REPLACE VIEW conservation_check AS SELECT (SELECT count(*) FROM typed) AS raw_n, (SELECT count(*) FROM all_out) AS out_n, (SELECT count(*) FROM (SELECT source_object, source_row FROM typed EXCEPT SELECT source_object, source_row FROM all_out)) AS lost_n, (SELECT count(*) FROM (SELECT source_object, source_row FROM all_out EXCEPT SELECT source_object, source_row FROM typed)) AS invented_n, (SELECT count(*) FROM (SELECT source_object, source_row FROM all_out GROUP BY 1,2 HAVING count(*) > 1)) AS overlap_or_dup_n, (SELECT count(*) - count(DISTINCT record_id) FROM curated) AS curated_dup_id_n;
""")

print("3. Dang xuat JSON...")
cursor_metrics = con.execute("SELECT * FROM metrics_after")
cols_m = [c[0] for c in cursor_metrics.description]
metrics = [dict(zip(cols_m, row)) for row in cursor_metrics.fetchall()]

for name, expected in T3["output_sha256"].items():
    actual = hashlib.sha256(Path("candidate", name).read_bytes()).hexdigest()
    assert actual == expected, f"CANDIDATE_MISMATCH: {name}"
envelope["candidate_sha256"] = T3["output_sha256"]

for m in metrics:
    m["run_id"] = RUN_ID
    m["contract_version"] = "research-telemetry-v1"

output = {
    **envelope,
    "checkpoint": "post-curation",
    "metrics": metrics
}
def custom_serializer(obj):
    if isinstance(obj, decimal.Decimal): return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

Path("quality_after.json").write_text(json.dumps(output, indent=2, default=custom_serializer))
print("==> DA TAO FILE quality_after.json THANH CONG!")

print("\n=======================================================")
print("==> CROSS-CHECK CONSERVATION CHO ROLE C:")
cursor_check = con.execute("SELECT * FROM conservation_check")
cols_check = [c[0] for c in cursor_check.description]
result = dict(zip(cols_check, cursor_check.fetchone()))
for k, v in result.items():
    print(f"{k}: {v}")
print("=======================================================")
