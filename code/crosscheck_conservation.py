import duckdb, json, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path
operator = sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN"
reviewer = sys.argv[2] if len(sys.argv) > 2 else "UNKNOWN"
con = duckdb.connect("work.duckdb")
def one(sql): return con.execute(sql).fetchone()[0]
KEY = "source_object, source_row"
res = {}
res["raw_n"] = one("SELECT count(*) FROM typed")
res["curated_n"] = one("SELECT count(*) FROM curated")
res["quarantine_n"] = one("SELECT count(*) FROM quarantine")
res["duplicates_n"] = one("SELECT count(*) FROM duplicates")
res["sum_matches"] = res["raw_n"] == res["curated_n"] + res["quarantine_n"] + res["duplicates_n"]
res["lost_n"] = one(f"SELECT count(*) FROM (SELECT {KEY} FROM typed EXCEPT SELECT {KEY} FROM all_out)")
res["invented_n"] = one(f"SELECT count(*) FROM (SELECT {KEY} FROM all_out EXCEPT SELECT {KEY} FROM typed)")
res["overlap_c_q"] = one(f"SELECT count(*) FROM (SELECT {KEY} FROM curated INTERSECT SELECT {KEY} FROM quarantine)")
res["overlap_c_d"] = one(f"SELECT count(*) FROM (SELECT {KEY} FROM curated INTERSECT SELECT {KEY} FROM duplicates)")
res["overlap_q_d"] = one(f"SELECT count(*) FROM (SELECT {KEY} FROM quarantine INTERSECT SELECT {KEY} FROM duplicates)")
for t in ("curated", "quarantine", "duplicates"):
    res[f"dup_phys_in_{t}"] = one(f"SELECT count(*) - count(DISTINCT ({KEY})) FROM {t}")
res["dup_record_id_curated"] = one("SELECT count(*) - count(DISTINCT record_id) FROM curated")
res["winners_not_in_curated_or_quarantine"] = one(
    f"SELECT count(*) FROM (SELECT {KEY} FROM winners EXCEPT (SELECT {KEY} FROM curated UNION SELECT {KEY} FROM quarantine))")
res["curated_or_quarantine_not_in_winners"] = one(
    f"SELECT count(*) FROM ((SELECT {KEY} FROM curated UNION SELECT {KEY} FROM quarantine) EXCEPT SELECT {KEY} FROM winners)")
res["pre_key_expected"] = one("SELECT parse_failures + key_rejected + ingest_parse_rejected FROM intake_counts")
res["superseded_missing_from_duplicates"] = one(
    f"SELECT count(*) FROM (SELECT {KEY} FROM key_eligible EXCEPT SELECT {KEY} FROM winners EXCEPT SELECT {KEY} FROM duplicates)")
res["duplicates_not_superseded"] = one(
    f"SELECT count(*) FROM (SELECT {KEY} FROM duplicates EXCEPT (SELECT {KEY} FROM key_eligible EXCEPT SELECT {KEY} FROM winners))")
checks = {
    "C01_counts_sum": res["sum_matches"],
    "C01_no_loss_no_invention": res["lost_n"] == 0 and res["invented_n"] == 0,
    "C01_pairwise_disjoint": res["overlap_c_q"] == res["overlap_c_d"] == res["overlap_q_d"] == 0,
    "C01_unique_physical_ids": all(res[f"dup_phys_in_{t}"] == 0 for t in ("curated", "quarantine", "duplicates")),
    "C01_curated_record_id_unique": res["dup_record_id_curated"] == 0,
    "B_every_winner_disposed": res["winners_not_in_curated_or_quarantine"] == 0,
    "B_non_winners_are_pre_key": res["curated_or_quarantine_not_in_winners"] == res["pre_key_expected"],
    "B_duplicates_equal_superseded": res["superseded_missing_from_duplicates"] == 0 and res["duplicates_not_superseded"] == 0,
}
out = {
    "check": "role-B independent recompute of role-C conservation/uniqueness",
    "operator": operator, "reviewer_of_artifact_owner": reviewer,
    "executed_at_utc": datetime.now(timezone.utc).isoformat(),
    "duckdb_version": duckdb.__version__,
    "candidate_sha256": {n: hashlib.sha256(Path("candidate", n).read_bytes()).hexdigest()
                         for n in ("curated.parquet", "quarantine.csv", "duplicates.csv")},
    "observed": res, "checks": checks, "PASS": all(checks.values()),
}
Path("evidence").mkdir(exist_ok=True)
Path("evidence/b-crosscheck-conservation.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
