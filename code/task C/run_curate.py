"""Driver for T3: run curate.sql, export outputs, run C01 / C02 / C03."""
import csv, hashlib, json, os, random, shutil, sys, tempfile, uuid
from pathlib import Path
import duckdb

HERE = Path(__file__).resolve().parent
EXPECTED = [("record_id","VARCHAR"),("sensor_id","VARCHAR"),("site","VARCHAR"),
            ("event_time_utc","TIMESTAMP"),("ingest_time_utc","TIMESTAMP"),
            ("temperature_c","DECIMAL(8,2)"),("is_late","BOOLEAN"),
            ("source_object","VARCHAR"),("source_row","BIGINT"),("source_sha256","VARCHAR")]

def find(obj, names, default):
    if isinstance(obj, dict):
        for n in names:
            if n in obj and not isinstance(obj[n], (dict, list)): return obj[n]
        for v in obj.values():
            r = find(v, names, None)
            if r is not None: return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, names, None)
            if r is not None: return r
    return default

def load_params(contract_path):
    c = json.loads(Path(contract_path).read_text()) if contract_path and Path(contract_path).exists() else {}
    as_of = str(find(c, ["as_of","AS_OF"], "2026-02-09T00:00:00Z"))
    return dict(as_of=as_of.replace("T"," ").rstrip("Z"),
             min_c=float(find(c, ["min_c","temp_min_c","min_temperature_c"], -30)),
             max_c=float(find(c, ["max_c","temp_max_c","max_temperature_c"], 60)),
             late_s=int(find(c, ["late_seconds","late_threshold_seconds","late_s"], 900)),
             id_pattern=str(find(c, ["id_pattern","record_id_pattern"], "R[0-9]{6}")))

def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def curate(workdir, out_dir, contract_path):
    cwd = os.getcwd(); os.chdir(workdir)
    try:
        out = Path(out_dir); out.mkdir(parents=True, exist_ok=False)
        p = load_params(contract_path)
        con = duckdb.connect()
        con.execute((HERE/"typed.sql").read_text())
        con.execute("CREATE TABLE params AS SELECT ?::TIMESTAMP AS as_of, ?::DOUBLE AS min_c, "
                    "?::DOUBLE AS max_c, ?::BIGINT AS late_s, ?::VARCHAR AS id_pattern",
                    [p["as_of"], p["min_c"], p["max_c"], p["late_s"], p["id_pattern"]])
        con.execute((HERE/"curate.sql").read_text())
        paths = dict(curated=str(out/"curated.parquet"), quarantine=str(out/"quarantine.csv"),
                     duplicates=str(out/"duplicates.csv"))
        con.execute(f"COPY (SELECT * FROM curated_out ORDER BY record_id) TO '{paths['curated']}' (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT * FROM quarantine_out ORDER BY source_object, source_row) TO '{paths['quarantine']}' (HEADER, DELIMITER ',')")
        con.execute(f"COPY (SELECT * FROM duplicates_out ORDER BY source_object, source_row) TO '{paths['duplicates']}' (HEADER, DELIMITER ',')")
        n_raw = con.execute("SELECT count(*) FROM raw_envelopes").fetchone()[0]
        reg_dup = con.execute("SELECT count(*) FROM registry_norm WHERE n>1").fetchone()[0]
        con.close()
        return dict(paths=paths, params=p, n_raw=n_raw, registry_dupes=reg_dup,
                    sha256={k: sha256_file(v) for k, v in paths.items()})
    finally:
        os.chdir(cwd)

def check_c01(res, workdir):
    con = duckdb.connect()
    cwd = os.getcwd(); os.chdir(workdir)
    try:
        con.execute("CREATE TABLE raw AS SELECT source_object, CAST(source_row AS BIGINT) AS source_row FROM read_csv('envelopes.csv', header=true, all_varchar=true)")
    finally:
        os.chdir(cwd)
    P = res["paths"]
    con.execute(f"CREATE TABLE c AS SELECT source_object, source_row, record_id FROM read_parquet('{P['curated']}')")
    for name in ("quarantine", "duplicates"):
        con.execute(f"CREATE TABLE {name[0]} AS SELECT source_object, CAST(source_row AS BIGINT) AS source_row FROM read_csv('{P[name]}', header=true, all_varchar=true)")
    q = lambda s: con.execute(s).fetchone()[0]
    k = "source_object, source_row"
    allout = f"SELECT {k} FROM c UNION ALL SELECT {k} FROM q UNION ALL SELECT {k} FROM d"
    r = {
      "n_raw": q("SELECT count(*) FROM raw"),
      "n_curated": q("SELECT count(*) FROM c"), "n_quarantine": q("SELECT count(*) FROM q"),
      "n_duplicates": q("SELECT count(*) FROM d"),
      "raw_minus_outputs": q(f"SELECT count(*) FROM (SELECT {k} FROM raw EXCEPT ({allout}))"),
      "outputs_minus_raw": q(f"SELECT count(*) FROM (({allout}) EXCEPT SELECT {k} FROM raw)"),
      "overlap_c_q": q(f"SELECT count(*) FROM (SELECT {k} FROM c INTERSECT SELECT {k} FROM q)"),
      "overlap_c_d": q(f"SELECT count(*) FROM (SELECT {k} FROM c INTERSECT SELECT {k} FROM d)"),
      "overlap_q_d": q(f"SELECT count(*) FROM (SELECT {k} FROM q INTERSECT SELECT {k} FROM d)"),
      "dup_phys_in_outputs": q(f"SELECT count(*) - count(DISTINCT ({k})) FROM ({allout})"),
      "dup_record_id_curated": q("SELECT count(*) - count(DISTINCT record_id) FROM c"),
    }
    r["sum_matches"] = r["n_raw"] == r["n_curated"] + r["n_quarantine"] + r["n_duplicates"]
    r["PASS"] = (r["sum_matches"] and all(r[x] == 0 for x in
        ["raw_minus_outputs","outputs_minus_raw","overlap_c_q","overlap_c_d","overlap_q_d",
         "dup_phys_in_outputs","dup_record_id_curated"]) and r["n_curated"] > 0)
    return r

def check_c03(res):
    con = duckdb.connect()
    got = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{res['paths']['curated']}')").fetchall()]
    names = [g[0] for g in got]
    return {"columns": got, "exact_10_columns_in_order": got == EXPECTED,
            "no_restricted": not ({"operator_email","raw_payload"} & set(names)),
            "PASS": got == EXPECTED}

def digest(res):
    con = duckdb.connect(); P = res["paths"]
    cur = con.execute(f"""SELECT sha256(string_agg(concat_ws('|',record_id,sensor_id,site,
        CAST(event_time_utc AS VARCHAR),CAST(ingest_time_utc AS VARCHAR),CAST(temperature_c AS VARCHAR),
        CAST(is_late AS VARCHAR),source_object,CAST(source_row AS VARCHAR),source_sha256),
        chr(10) ORDER BY record_id)) FROM read_parquet('{P['curated']}')""").fetchone()[0]
    qua = con.execute(f"""SELECT sha256(string_agg(concat_ws('|',source_object,source_row,record_id,stage,
        primary_reason,all_reasons),chr(10) ORDER BY source_object,CAST(source_row AS BIGINT)))
        FROM read_csv('{P['quarantine']}',header=true,all_varchar=true)""").fetchone()[0]
    dup = con.execute(f"""SELECT sha256(string_agg(concat_ws('|',source_object,source_row,record_id,reason,
        winner_source_object,winner_source_row),chr(10) ORDER BY source_object,CAST(source_row AS BIGINT)))
        FROM read_csv('{P['duplicates']}',header=true,all_varchar=true)""").fetchone()[0]
    return dict(curated=cur, quarantine=qua, duplicates=dup)

def reordered_copy(src_workdir, dst, mode, seed=7):
    dst = Path(dst); dst.mkdir(parents=True)
    shutil.copytree(Path(src_workdir)/"snapshot", dst/"snapshot")
    with open(Path(src_workdir)/"envelopes.csv", newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f); rows = list(rd); fields = rd.fieldnames
    if mode == "reversed": rows.reverse()
    elif mode == "shuffled": random.Random(seed).shuffle(rows)
    with open(dst/"envelopes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    return dst

def check_c02(workdir, contract_path, tmp):
    digs = {}
    for mode in ("original", "reversed", "shuffled"):
        wd = workdir if mode == "original" else reordered_copy(workdir, Path(tmp)/mode, mode)
        res = curate(wd, Path(tmp)/f"out_{mode}", contract_path)
        digs[mode] = digest(res)
    return {"digests": digs, "PASS": all(digs[m] == digs["original"] for m in digs)}

def main():
    workdir = Path(".").resolve(); contract = "contract.json"
    run_id = uuid.uuid4().hex[:8]
    res = curate(workdir, Path("candidate")/f"run-{run_id}", contract)
    ev = {"run_id": run_id, "params_used": res["params"], "registry_duplicate_ids": res["registry_dupes"],
          "output_sha256": res["sha256"], "C01": check_c01(res, workdir), "C03": check_c03(res)}
    if "--replay" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            ev["C02"] = check_c02(workdir, contract, tmp)
    Path("evidence").mkdir(exist_ok=True)
    Path(f"evidence/curate-checks-{run_id}.json").write_text(json.dumps(ev, indent=2, default=str))
    print(json.dumps({k: (v["PASS"] if isinstance(v, dict) and "PASS" in v else v)
                      for k, v in ev.items() if k in ("run_id","C01","C02","C03")}, indent=2))

if __name__ == "__main__":
    main()
