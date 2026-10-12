# Defect investigation (Lab 2, T2)

Run: 8c68ba1d (curate run 8c68ba1d), contract research-telemetry-v1, AS_OF 2026-02-09T00:00:00Z.
Counts come from SQL (quality.sql, run_before.py, run_after.py). Samples are source references only; no email or raw payload is included.

## Population accounting

| Stage | Count |
|---|---|
| Raw physical records | 10205 |
| Parse failures (PARSE) | 5 |
| Key rejected (KEY) | 20 |
| Ingest time unparseable (INGEST_PARSE) | 20 |
| Key-eligible before dedup | 10160 |
| Superseded duplicates | 200 |
| Winners W (before row validity) | 9960 |
| Winners quarantined as invalid | 350 |
| Curated | 9610 |
| Quarantine ledger total | 395 |
| Duplicate ledger total | 200 |

## Defect categories on winners W (disjoint, primary reason)

| Category | Rule | Count (of W) | Rule violated | Disposition | Sample refs (source#row) |
|---|---|---|---|---|---|
| REQUIRED | Q_REQUIRED | 110 | a required field is blank or NULL | quarantined, no imputation | observations_a.csv#1, observations_a.csv#2, observations_a.csv#3, observations_b.jsonl#5151, observations_b.jsonl#5152, observations_b.jsonl#5153 |
| VALUE | Q_VALUE | 140 | non-numeric or non-finite reading, unsupported unit, or temperature outside [-30, 60] C | quarantined | observations_a.csv#101, observations_a.csv#102, observations_a.csv#103 |
| TIME | Q_TIME | 70 | unparseable timestamp, event_time > ingest_time, or ingest_time > AS_OF | quarantined | observations_a.csv#241, observations_a.csv#242, observations_a.csv#243 |
| REFERENCE | Q_REFINT | 30 | sensor_id not found in the sensor registry | quarantined | observations_a.csv#311, observations_a.csv#312, observations_a.csv#313 |
| LATE | Q_TIMELY | 200 | lag_seconds > 900 on an otherwise valid row | retained, is_late = true | observations_a.csv#381, observations_a.csv#382, observations_a.csv#383 |

### Breakdown of the categories above (from the quarantine ledger)

- VALUE 140 = NUMERIC 60 (reading not a finite number) + UNIT 40 (unit other than C/F) + RANGE 40 (converted temperature outside [-30, 60] C).
- TIME 70 = TIME_PARSE 40 (timestamp not in YYYY-MM-DDTHH:MM:SSZ) + TIME_ORDER 30 (event_time after ingest_time or ingest_time after AS_OF).
- REQUIRED 110: every one also carries NUMERIC and RANGE (a blank reading cannot be converted), so Q_VALUE failures = VALUE + REQUIRED.
- Before dedup: PARSE 5 (malformed JSON), KEY 20 (missing or invalid record_id), INGEST_PARSE 20 (unparseable arrival time).

Check: REQUIRED+VALUE+TIME+REFERENCE = 350; W - curated = 350; MATCH.
Q_VALUE failures (250) include the REQUIRED rows with a NULL reading, so Q_VALUE and Q_REQUIRED overlap; categories above use the primary reason to stay disjoint.

## Quarantine ledger by stage and primary reason

| Stage | Primary reason | Count |
|---|---|---|
| WINNER_VALIDATION | REQUIRED | 110 |
| WINNER_VALIDATION | NUMERIC | 60 |
| WINNER_VALIDATION | UNIT | 40 |
| WINNER_VALIDATION | RANGE | 40 |
| WINNER_VALIDATION | TIME_PARSE | 40 |
| WINNER_VALIDATION | TIME_ORDER | 30 |
| WINNER_VALIDATION | REFERENCE | 30 |
| PRE_KEY | KEY | 20 |
| PRE_KEY | INGEST_PARSE | 20 |
| PRE_KEY | PARSE | 5 |

## Quarantine ledger by all failing reasons (combinations)

| all_reasons | Count |
|---|---|
| REQUIRED|NUMERIC|RANGE | 110 |
| NUMERIC|RANGE | 60 |
| UNIT|RANGE | 40 |
| RANGE | 40 |
| TIME_PARSE|TIME_ORDER | 40 |
| TIME_ORDER | 30 |
| REFERENCE | 30 |
| KEY | 20 |
| INGEST_PARSE | 20 |
| PARSE|KEY|INGEST_PARSE | 5 |

## Duplicate ledger by reason

| Reason | Count |
|---|---|
| SUPERSEDED | 200 |

## Retained vs rejected, and late data

- Retained in curated: 9610/10205 = 94.2% of raw, and 9610/9960 = 96.5% of W.
- Quarantined: 395/10205 = 3.9% of raw. Superseded duplicates: 200/10205 = 2.0% of raw.
- Required, unique, value, registry and time rules reach 100% after curation because failing rows were removed, not because missing or invalid values were recovered.
- Late observations: 200 before and 200 after. All late rows were retained and flagged. Q_TIMELY moves 0.9798 -> 0.9792 only because its denominator shrank (9890 -> 9610), not because the data got worse.
- Reference sample: agreement 95/100 (threshold 0.95, exactly at the limit), coverage 100/100. This describes the supplied sample only, not the accuracy of every real reading.
