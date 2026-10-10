# Research Telemetry Curated Dataset

## Purpose

This dataset is the curated output of the Lab 2 research-telemetry pipeline. It contains validated synthetic temperature observations intended only for teaching and laboratory use. The pipeline preserves provenance from the original source objects and records enough metadata to support reproducibility, auditing, and release governance.

## Data Sources

The source observations are stored in the `research-raw` object store. The primary observation inputs are `observations_a.csv` and `observations_b.jsonl`, with `sensors.csv` used as the sensor registry and the observation contract defining validation rules. The staged intake contains 10,205 physical records.

## Curated Schema

The curated dataset contains 9,610 rows and exactly ten columns: `record_id`, `sensor_id`, `site`, `event_time_utc`, `ingest_time_utc`, `temperature_c`, `is_late`, `source_object`, `source_row`, and `source_sha256`. Temperature values are represented in degrees Celsius. Timestamps are normalized to UTC.

## Curation and Quality

Records are parsed, keyed, deduplicated, validated, and enriched with site information. Non-winning duplicate rows are separated into `duplicates.csv`, while invalid rows are written to `quarantine.csv`. The curation conservation check confirms that all 10,205 physical input records are accounted for by 9,610 curated rows, 395 quarantine rows, and 200 duplicate rows.

Post-curation quality checks passed the required thresholds. Required-field completeness, uniqueness, value validity, reference integrity, and timestamp validity all achieved 1.0. Timeliness achieved 0.9792 against a 0.95 threshold.

## Access and Retention

Quarantine and duplicate artifacts are restricted and must not be included in analyst-facing approved releases. Raw input is retained for 30 days, quarantine data for 7 days, and approved releases for 90 days, subject to legal-hold and active-dependency overrides.

## Reproduction

The catalog records the trusted-manifest hash, contract hash, code hash, output hashes, curation run identifier, quality-report location, and source-level provenance required to reproduce and verify the run.
