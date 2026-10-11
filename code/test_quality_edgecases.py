"""Role B tests.
  Part 1: quality.sql edge cases on a tiny fixture with hand-computed expectations.
  Part 2: negative control showing the anti-join conservation check catches
          "one lost + one duplicated record" even when the totals still match.
Run from the repo root:   python3 code/test_quality_edgecases.py
Writes evidence/b-unit-test-quality.json
"""
import csv, json, os, sys, tempfile
from pathlib import Path
import duckdb

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
TYPED = (HERE / "typed.sql").read_text()
QUALITY = (HERE / "quality.sql").read_text().split("CREATE OR REPLACE VIEW curated")[0]

FIELDS = ["record_id", "sensor_id", "event_time", "ingest_time", "reading", "unit",
          "operator_email", "source_object", "source_row", "source_sha256",
          "parse_ok", "raw_payload"]


def row(n, rid, sensor="S01", ev="2026-01-01T00:00:00Z", ing="2026-01-01T00:05:00Z",
        reading="20", unit="C"):
    return dict(record_id=rid, sensor_id=sensor, event_time=ev, ingest_time=ing,
                reading=reading, unit=unit, operator_email="",
                source_object="s3://test/a.csv", source_row=n,
                source_sha256="0" * 64, parse_ok="true", raw_payload="{}")


def build(rows):
    td = Path(tempfile.mkdtemp())
    (td / "snapshot").mkdir()
    with (td / "envelopes.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (td / "snapshot/sensors.csv").write_text("sensor_id,site\nS01,Hanoi\n")
    (td / "snapshot/qa_reference.csv").write_text("record_id,reference_c\nR000001,20.00\n")
    os.chdir(td)
    con = duckdb.connect()
    for sql in (TYPED, QUALITY):
        for stmt in sql.split(";"):
            if stmt.strip():
                con.execute(stmt)
    return con


def metrics(con):
    q = "SELECT rule_id, numerator, denominator, value, status FROM metrics_before"
    return {r[0]: (r[1], r[2], r[3], r[4]) for r in con.execute(q).fetchall()}


results = []


def check(name, ok, observed, expected):
    results.append(dict(test=name, passed=bool(ok), observed=observed, expected=expected))


rows = [
    row(1, "R000001"),
    row(2, "R000002", ing="2026-01-01T00:30:00Z", reading="32", unit="F"),
    row(3, "R000003", reading=""),
    row(4, "R000004", reading="300"),
    row(5, "R000005", unit="K"),
    row(6, "R000006", sensor="S99"),
    row(7, "R000007", ev="2026-01-01T01:00:00Z"),
    row(8, "R000008"),
    row(9, "R000008", ing="2026-01-01T00:10:00Z", reading="500"),
    row(10, "X1"),
]
con = build(rows)
m = metrics(con)
expected = {
    "Q_REQUIRED": (7, 8), "Q_UNIQUE": (8, 9), "Q_VALUE": (4, 8),
    "Q_REFINT": (7, 8), "Q_TIME": (7, 8), "Q_TIMELY": (6, 7),
}
for rule, (n, d) in expected.items():
    check(f"fixture_{rule}", m[rule][:2] == (n, d), list(m[rule][:2]), [n, d])

ic = con.execute("SELECT raw_total, key_rejected, key_eligible, winners_W, duplicate_excess "
                 "FROM intake_counts").fetchone()
check("fixture_intake_counts", ic == (10, 1, 9, 8, 1), list(ic), [10, 1, 9, 8, 1])

win = con.execute("SELECT source_row FROM winners WHERE record_id='R000008'").fetchall()
check("newer_invalid_version_wins", win == [(9,)], win, [[9]])

con = build([])
m0 = metrics(con)
ok = all(v[1] == 0 and v[2] is None and v[3] == "NOT_EVALUATED" for v in m0.values())
check("zero_denominator_not_evaluated", ok, {k: v[3] for k, v in m0.items()}, "all NOT_EVALUATED, value NULL")

os.chdir(ROOT)


def conservation(curated, quarantine, duplicates):
    c = duckdb.connect()
    c.execute("CREATE TABLE typed AS SELECT 'a' AS source_object, i AS source_row FROM range(1,6) t(i)")
    for name, ids in (("curated", curated), ("quarantine", quarantine), ("duplicates", duplicates)):
        vals = ",".join(f"('a',{i})" for i in ids)
        c.execute(f"CREATE TABLE {name} AS SELECT * FROM (VALUES {vals}) t(source_object, source_row)")
    c.execute("""CREATE VIEW all_out AS
        SELECT * FROM curated UNION ALL SELECT * FROM quarantine UNION ALL SELECT * FROM duplicates""")
    raw_n = c.execute("SELECT count(*) FROM typed").fetchone()[0]
    out_n = c.execute("SELECT count(*) FROM all_out").fetchone()[0]
    lost = c.execute("SELECT count(*) FROM (SELECT * FROM typed EXCEPT SELECT * FROM all_out)").fetchone()[0]
    dup = c.execute("SELECT count(*) FROM (SELECT source_object, source_row FROM all_out "
                    "GROUP BY 1,2 HAVING count(*)>1)").fetchone()[0]
    return raw_n == out_n, lost, dup


same_total, lost, dup = conservation([1, 2], [3], [4, 4])
check("negative_control_total_matches_but_defect_caught",
      same_total and lost == 1 and dup == 1,
      dict(totals_equal=same_total, lost=lost, duplicated=dup),
      dict(totals_equal=True, lost=1, duplicated=1))
same_total, lost, dup = conservation([1, 2], [3], [4, 5])
check("positive_control_clean_partition", same_total and lost == 0 and dup == 0,
      dict(totals_equal=same_total, lost=lost, duplicated=dup),
      dict(totals_equal=True, lost=0, duplicated=0))

all_pass = all(r["passed"] for r in results)
Path("evidence").mkdir(exist_ok=True)
Path("evidence/b-unit-test-quality.json").write_text(
    json.dumps(dict(PASS=all_pass, duckdb=duckdb.__version__, results=results), indent=2, default=str))
for r in results:
    print(("PASS " if r["passed"] else "FAIL ") + r["test"], "" if r["passed"] else r)
print("OVERALL:", "PASS" if all_pass else "FAIL")
sys.exit(0 if all_pass else 1)
