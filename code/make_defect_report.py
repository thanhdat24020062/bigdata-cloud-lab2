import json
from pathlib import Path

here = Path(__file__).parent
bef = json.loads((here / 'quality_before.json').read_text())
aft = json.loads((here / 'quality_after.json').read_text())
dd = json.loads((here / 'evidence' / 'defect_data.json').read_text())
inv = bef['raw_inventory']
mb = {m['rule_id']: m for m in bef['metrics']}
ma = {m['rule_id']: m for m in aft['metrics']}
raw, W = inv['raw_total'], inv['winners_W']
n_cur, n_q, n_d = dd['n_curated'], dd['n_quarantine'], dd['n_duplicates']
assert n_cur + n_q + n_d == raw, 'conservation broken'
cats = dd['category_counts']
qr = {p: n for s, p, n in dd['quarantine_by_reason']}
invalid_w = sum(cats.get(k, 0) for k in ('REQUIRED', 'VALUE', 'TIME', 'REFERENCE'))
late_b = mb['Q_TIMELY']['denominator'] - mb['Q_TIMELY']['numerator']
late_a = ma['Q_TIMELY']['denominator'] - ma['Q_TIMELY']['numerator']

L = ["# Defect investigation (Lab 2, T2)\n",
     f"Run: {aft['run_id']} (curate run {aft['curate_run_id']}), contract {aft['contract_version']}, AS_OF {aft['as_of']}.",
     "Counts come from SQL (quality.sql, run_before.py, run_after.py). Samples are source references only; no email or raw payload is included.\n",
     "## Population accounting\n", "| Stage | Count |", "|---|---|",
     f"| Raw physical records | {raw} |",
     f"| Parse failures (PARSE) | {inv['parse_failures']} |",
     f"| Key rejected (KEY) | {inv['key_rejected']} |",
     f"| Ingest time unparseable (INGEST_PARSE) | {inv['ingest_parse_rejected']} |",
     f"| Key-eligible before dedup | {inv['key_eligible']} |",
     f"| Superseded duplicates | {inv['duplicate_excess']} |",
     f"| Winners W (before row validity) | {W} |",
     f"| Winners quarantined as invalid | {W - n_cur} |",
     f"| Curated | {n_cur} |",
     f"| Quarantine ledger total | {n_q} |",
     f"| Duplicate ledger total | {n_d} |\n",
     "## Defect categories on winners W (disjoint, primary reason)\n",
     "| Category | Rule | Count (of W) | Rule violated | Disposition | Sample refs (source#row) |", "|---|---|---|---|---|---|"]
rows = [('REQUIRED', 'Q_REQUIRED', 'a required field is blank or NULL', 'quarantined, no imputation'),
        ('VALUE', 'Q_VALUE', 'non-numeric or non-finite reading, unsupported unit, or temperature outside [-30, 60] C', 'quarantined'),
        ('TIME', 'Q_TIME', 'unparseable timestamp, event_time > ingest_time, or ingest_time > AS_OF', 'quarantined'),
        ('REFERENCE', 'Q_REFINT', 'sensor_id not found in the sensor registry', 'quarantined'),
        ('LATE', 'Q_TIMELY', 'lag_seconds > 900 on an otherwise valid row', 'retained, is_late = true')]
for k, rule, cause, disp in rows:
    L.append(f"| {k} | {rule} | {cats.get(k, 0)} | {cause} | {disp} | {', '.join(dd['samples'].get(k, []))} |")
L.append("")
L.append("### Breakdown of the categories above (from the quarantine ledger)\n")
L.append(f"- VALUE {cats.get('VALUE', 0)} = NUMERIC {qr.get('NUMERIC', 0)} (reading not a finite number) + UNIT {qr.get('UNIT', 0)} (unit other than C/F) + RANGE {qr.get('RANGE', 0)} (converted temperature outside [-30, 60] C).")
L.append(f"- TIME {cats.get('TIME', 0)} = TIME_PARSE {qr.get('TIME_PARSE', 0)} (timestamp not in YYYY-MM-DDTHH:MM:SSZ) + TIME_ORDER {qr.get('TIME_ORDER', 0)} (event_time after ingest_time or ingest_time after AS_OF).")
L.append(f"- REQUIRED {cats.get('REQUIRED', 0)}: every one also carries NUMERIC and RANGE (a blank reading cannot be converted), so Q_VALUE failures = VALUE + REQUIRED.")
L.append(f"- Before dedup: PARSE {qr.get('PARSE', 0)} (malformed JSON), KEY {qr.get('KEY', 0)} (missing or invalid record_id), INGEST_PARSE {qr.get('INGEST_PARSE', 0)} (unparseable arrival time).\n")
L.append(f"Check: REQUIRED+VALUE+TIME+REFERENCE = {invalid_w}; W - curated = {W - n_cur}; {'MATCH' if invalid_w == W - n_cur else 'MISMATCH'}.")
L.append(f"Q_VALUE failures ({mb['Q_VALUE']['denominator'] - mb['Q_VALUE']['numerator']}) include the REQUIRED rows with a NULL reading, so Q_VALUE and Q_REQUIRED overlap; categories above use the primary reason to stay disjoint.\n")
L += ["## Quarantine ledger by stage and primary reason\n", "| Stage | Primary reason | Count |", "|---|---|---|"]
L += [f"| {s} | {p} | {n} |" for s, p, n in dd['quarantine_by_reason']]
L += ["", "## Quarantine ledger by all failing reasons (combinations)\n", "| all_reasons | Count |", "|---|---|"]
L += [f"| {a} | {n} |" for a, n in dd['quarantine_reason_combos']]
L += ["", "## Duplicate ledger by reason\n", "| Reason | Count |", "|---|---|"]
L += [f"| {r} | {n} |" for r, n in dd['duplicates_by_reason']]
L += ["", "## Retained vs rejected, and late data\n",
      f"- Retained in curated: {n_cur}/{raw} = {n_cur/raw:.1%} of raw, and {n_cur}/{W} = {n_cur/W:.1%} of W.",
      f"- Quarantined: {n_q}/{raw} = {n_q/raw:.1%} of raw. Superseded duplicates: {n_d}/{raw} = {n_d/raw:.1%} of raw.",
      "- Required, unique, value, registry and time rules reach 100% after curation because failing rows were removed, not because missing or invalid values were recovered.",
      f"- Late observations: {late_b} before and {late_a} after. All late rows were retained and flagged. Q_TIMELY moves {mb['Q_TIMELY']['value']:.4f} -> {ma['Q_TIMELY']['value']:.4f} only because its denominator shrank ({mb['Q_TIMELY']['denominator']} -> {ma['Q_TIMELY']['denominator']}), not because the data got worse.",
      f"- Reference sample: agreement {ma['Q_REF_AGREE']['numerator']}/{ma['Q_REF_AGREE']['denominator']} (threshold 0.95, exactly at the limit), coverage {ma['Q_REF_COVERAGE']['numerator']}/{ma['Q_REF_COVERAGE']['denominator']}. This describes the supplied sample only, not the accuracy of every real reading."]
(here / 'defect_report.md').write_text("\n".join(L) + "\n", encoding='utf-8')
print("\n".join(L))
