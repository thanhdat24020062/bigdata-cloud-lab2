"""C04: the four required counterexamples (+ extra rules) on a small fixture."""
import csv, json, tempfile, sys
from pathlib import Path
import duckdb
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_curate as rc

A, B = "s3://x/observations_a.csv", "s3://x/observations_b.jsonl"
FIELDS = ["record_id","sensor_id","event_time","ingest_time","reading","unit","operator_email",
          "source_object","source_row","source_sha256","parse_ok","raw_payload"]
def row(obj, n, rid, sid="S01", ev="2026-01-01T10:00:00Z", ing="2026-01-01T10:05:00Z",
        val="20", unit="C", email="", ok="true"):
    return dict(record_id=rid, sensor_id=sid, event_time=ev, ingest_time=ing, reading=val, unit=unit,
                operator_email=email, source_object=obj, source_row=n, source_sha256="a"*64,
                parse_ok=ok, raw_payload="{}")
ROWS = [
  row(A,1,"R000001",val="32",unit="F"),
  row(A,2,"R000002",val="300",unit="K"),
  row(A,3,"R000003",val="nan"),
  row(A,4,"R000004",ing="2026-01-01T10:00:00Z",val="21"),
  row(B,1,"R000004",ing="2026-01-01T11:00:00Z",val="100"),
  row(A,5,"R000005",ev="2026-01-01T09:00:00Z",ing="2026-01-01T10:00:00Z"),
  row(A,6,"",ok="false",val="",unit="",sid="",ev="",ing=""),
  row(A,7,"X1"),
  row(A,8,"R000008",ing="not-a-time"),
  row(A,9,"R000009"), row(B,2,"R000009"),
  row(A,10,"R000010",sid="S99"),
  row(A,11,"R000011",ev="2026-01-01T12:00:00Z"),
  row(A,12,"  r000012 ",sid=" s01 ",unit="c",email="x@y.z"),
  row(A,13,"R000013",ing="2026-03-01T00:00:00Z"),
  row(A,14,"R000014",val=""),
]
def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); (t/"snapshot").mkdir()
        (t/"snapshot/sensors.csv").write_text("sensor_id,site\nS01,Hanoi\nS02,Hue\n")
        (t/"snapshot/qa_reference.csv").write_text("record_id,reference_c\nR000001,0.00\n")
        with open(t/"envelopes.csv","w",newline="",encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(ROWS)
        res = rc.curate(t, t/"out", None)
        con = duckdb.connect(); P = res["paths"]
        cur = {r[0]: r for r in con.execute(f"SELECT record_id,temperature_c,is_late,site,source_object,source_row FROM read_parquet('{P['curated']}')").fetchall()}
        qua = {(r[0],int(r[1])): r for r in con.execute(f"SELECT source_object,source_row,primary_reason,all_reasons FROM read_csv('{P['quarantine']}',header=true,all_varchar=true)").fetchall()}
        dup = {(r[0],int(r[1])): r for r in con.execute(f"SELECT source_object,source_row,winner_source_object,winner_source_row FROM read_csv('{P['duplicates']}',header=true,all_varchar=true)").fetchall()}
        T = []
        def t_(name, ok, detail=""): T.append(dict(test=name, PASS=bool(ok), detail=str(detail)))
        t_("C04.1  32F -> 0.00 retained, blank email OK", str(cur["R000001"][1]) == "0.00", cur.get("R000001"))
        t_("C04.2a unit K quarantined (UNIT)", qua.get((A,2),[0]*4)[2] == "UNIT", qua.get((A,2)))
        t_("C04.2b nan quarantined (NUMERIC)", qua.get((A,3),[0]*4)[2] == "NUMERIC", qua.get((A,3)))
        t_("C04.4a newer invalid winner quarantined (RANGE)", qua.get((B,1),[0]*4)[2] == "RANGE", qua.get((B,1)))
        t_("C04.4b older valid version -> duplicates, not curated", (A,4) in dup and "R000004" not in cur, dup.get((A,4)))
        t_("late row retained, is_late=true", cur["R000005"][2] is True, cur.get("R000005"))
        t_("PARSE primary", qua.get((A,6),[0]*4)[2] == "PARSE", qua.get((A,6)))
        t_("KEY primary", qua.get((A,7),[0]*4)[2] == "KEY", qua.get((A,7)))
        t_("INGEST_PARSE primary", qua.get((A,8),[0]*4)[2] == "INGEST_PARSE", qua.get((A,8)))
        t_("tie: lower source_object wins", cur.get("R000009",[0]*6)[4] == A and (B,2) in dup, (cur.get("R000009"), dup.get((B,2))))
        t_("unknown sensor -> REFERENCE", qua.get((A,10),[0]*4)[2] == "REFERENCE", qua.get((A,10)))
        t_("event>ingest -> TIME_ORDER", qua.get((A,11),[0]*4)[2] == "TIME_ORDER", qua.get((A,11)))
        t_("normalization retained R000012 with site", cur.get("R000012",[0]*4)[3] == "Hanoi", cur.get("R000012"))
        t_("ingest after AS_OF -> TIME_ORDER", qua.get((A,13),[0]*4)[2] == "TIME_ORDER", qua.get((A,13)))
        t_("missing reading -> REQUIRED primary", qua.get((A,14),[0]*4)[2] == "REQUIRED", qua.get((A,14)))
        c01 = rc.check_c01(res, t); c03 = rc.check_c03(res)
        t_("C01 conservation on fixture", c01["PASS"], c01)
        t_("C03 schema/privacy on fixture", c03["PASS"], c03["columns"])
        with tempfile.TemporaryDirectory() as tmp:
            c02 = rc.check_c02(t, None, tmp)
        t_("C02 replay equivalence on fixture", c02["PASS"], "")
        for x in T: print(("PASS " if x["PASS"] else "FAIL ") + x["test"] + ("" if x["PASS"] else "  -> " + x["detail"]))
        print(f"\n{sum(x['PASS'] for x in T)}/{len(T)} passed")
        Path("evidence").mkdir(exist_ok=True)
        Path("evidence/c04-results.json").write_text(json.dumps(T, indent=2))
        sys.exit(0 if all(x["PASS"] for x in T) else 1)
main()
