CREATE OR REPLACE TABLE params AS
SELECT strptime('2026-02-09T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ') AS as_of,
       900   AS late_s,
       -30.0 AS tmin, 
       60.0  AS tmax,
       0.05  AS tol;

CREATE OR REPLACE VIEW registry_n AS
SELECT upper(trim(sensor_id)) AS sensor_id, site FROM registry;

CREATE OR REPLACE VIEW intake_flags AS
SELECT *,
  coalesce(parse_ok, false) AS f_parse,
  coalesce(regexp_full_match(record_id, 'R[0-9]{6}'), false) AS f_key,
  (ingest_ts IS NOT NULL) AS f_ingest
FROM typed;

CREATE OR REPLACE VIEW key_eligible AS
SELECT * FROM intake_flags WHERE f_parse AND f_key AND f_ingest;

CREATE OR REPLACE VIEW winners AS
SELECT * EXCLUDE (rn) FROM (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY record_id
    ORDER BY ingest_ts DESC, source_object ASC, source_row ASC) AS rn
  FROM key_eligible)
WHERE rn = 1;

CREATE OR REPLACE VIEW intake_counts AS
SELECT
  (SELECT count(*) FROM typed)                                                AS raw_total,
  (SELECT count(*) FROM intake_flags WHERE NOT f_parse)                       AS parse_failures,
  (SELECT count(*) FROM intake_flags WHERE f_parse AND NOT f_key)             AS key_rejected,
  (SELECT count(*) FROM intake_flags WHERE f_parse AND f_key AND NOT f_ingest) AS ingest_parse_rejected,
  (SELECT count(*) FROM key_eligible)                                         AS key_eligible,
  (SELECT count(*) FROM winners)                                              AS winners_W,
  (SELECT count(*) FROM key_eligible) - (SELECT count(*) FROM winners)        AS duplicate_excess,
  (SELECT count(*) FROM intake_flags WHERE f_parse AND NOT (
      nullif(trim(record_id),'') IS NOT NULL AND nullif(trim(sensor_id),'') IS NOT NULL AND
      nullif(trim(event_time),'') IS NOT NULL AND nullif(trim(ingest_time),'') IS NOT NULL AND
      nullif(trim(reading),'') IS NOT NULL AND nullif(trim(unit),'') IS NOT NULL)) AS required_fail_parsed_intake;

CREATE OR REPLACE VIEW w_flags AS
WITH c AS (
  SELECT w.*,
    CASE unit WHEN 'C' THEN value_num
              WHEN 'F' THEN (value_num - 32) * 5.0 / 9 END AS temp_c_raw
  FROM winners w)
SELECT c.*,
  (nullif(trim(record_id),'') IS NOT NULL AND nullif(trim(sensor_id),'') IS NOT NULL AND
   nullif(trim(event_time),'') IS NOT NULL AND nullif(trim(ingest_time),'') IS NOT NULL AND
   nullif(trim(reading),'') IS NOT NULL AND nullif(trim(unit),'') IS NOT NULL)      AS f_required,
  coalesce(isfinite(value_num) AND unit IN ('C','F')
           AND temp_c_raw BETWEEN p.tmin AND p.tmax, false)                         AS f_value,
  coalesce(sensor_id IN (SELECT sensor_id FROM registry_n), false)                  AS f_ref,
  coalesce(event_ts IS NOT NULL AND ingest_ts IS NOT NULL
           AND event_ts <= ingest_ts AND ingest_ts <= p.as_of, false)               AS f_time,
  coalesce(epoch(ingest_ts) - epoch(event_ts) <= p.late_s, false)                   AS f_timely
FROM c CROSS JOIN params p;

CREATE OR REPLACE VIEW metrics_before_raw AS
SELECT 'Q_REQUIRED' AS rule_id, 'W: winners trước row-validity' AS cohort,
       count(*) FILTER (WHERE f_required) AS numerator, count(*) AS denominator,
       1.0 AS threshold, 'BLOCK' AS severity FROM w_flags
UNION ALL SELECT 'Q_UNIQUE', 'key-eligible trước dedup (distinct record_id / rows)',
       (SELECT count(DISTINCT record_id) FROM key_eligible), (SELECT count(*) FROM key_eligible), 1.0, 'BLOCK'
UNION ALL SELECT 'Q_VALUE', 'W before curation', count(*) FILTER (WHERE f_value), count(*), 1.0, 'BLOCK' FROM w_flags
UNION ALL SELECT 'Q_REFINT', 'W before curation', count(*) FILTER (WHERE f_ref), count(*), 1.0, 'BLOCK' FROM w_flags
UNION ALL SELECT 'Q_TIME', 'W before curation', count(*) FILTER (WHERE f_time), count(*), 1.0, 'BLOCK' FROM w_flags
UNION ALL SELECT 'Q_TIMELY', 'W rows với event<=ingest<=AS_OF',
       count(*) FILTER (WHERE f_time AND f_timely), count(*) FILTER (WHERE f_time), 0.95, 'BLOCK' FROM w_flags;

CREATE OR REPLACE VIEW metrics_before AS
SELECT 
    rule_id,
    'pre-curated' AS dataset_id,
    cohort,
    numerator,
    denominator,
    CASE WHEN denominator = 0 THEN NULL ELSE round(cast(numerator AS DOUBLE) / denominator, 4) END AS value,
    threshold,
    severity,
    CASE WHEN denominator = 0 THEN 'NOT_EVALUATED' ELSE 'EVALUATED' END AS status
FROM metrics_before_raw;

CREATE OR REPLACE VIEW defect_samples AS
SELECT 'REQUIRED' AS category, source_object, source_row FROM w_flags WHERE NOT f_required
UNION ALL SELECT 'VALUE', source_object, source_row FROM w_flags WHERE f_required AND NOT f_value
UNION ALL SELECT 'REFERENCE', source_object, source_row FROM w_flags WHERE NOT f_ref
UNION ALL SELECT 'TIME', source_object, source_row FROM w_flags WHERE NOT f_time
UNION ALL SELECT 'LATE', source_object, source_row FROM w_flags WHERE f_time AND NOT f_timely;

CREATE OR REPLACE VIEW curated AS SELECT * FROM read_parquet('candidate/curated.parquet');

CREATE OR REPLACE VIEW quarantine AS 
  SELECT source_object, try_cast(source_row AS BIGINT) AS source_row 
  FROM read_csv('candidate/quarantine.csv', all_varchar=true);

CREATE OR REPLACE VIEW duplicates AS 
  SELECT source_object, try_cast(source_row AS BIGINT) AS source_row 
  FROM read_csv('candidate/duplicates.csv', all_varchar=true);

CREATE OR REPLACE VIEW ref_match AS
SELECT c.record_id, c.temperature_c, q.reference_c,
       abs(c.temperature_c - q.reference_c) <= (SELECT tol FROM params) AS agrees
FROM curated c JOIN qa_reference q USING (record_id);

CREATE OR REPLACE VIEW metrics_after_raw AS
SELECT 'Q_REQUIRED' AS rule_id, 'curated candidate' AS cohort,
       count(*) FILTER (WHERE record_id IS NOT NULL AND sensor_id IS NOT NULL AND event_time_utc IS NOT NULL
                          AND ingest_time_utc IS NOT NULL AND temperature_c IS NOT NULL) AS numerator,
       count(*) AS denominator, 1.0 AS threshold, 'BLOCK' AS severity FROM curated
UNION ALL SELECT 'Q_UNIQUE', 'curated candidate (distinct record_id / rows)',
       count(DISTINCT record_id), count(*), 1.0, 'BLOCK' FROM curated
UNION ALL SELECT 'Q_VALUE', 'curated candidate',
       count(*) FILTER (WHERE temperature_c BETWEEN (SELECT tmin FROM params) AND (SELECT tmax FROM params)),
       count(*), 1.0, 'BLOCK' FROM curated
UNION ALL SELECT 'Q_REFINT', 'curated candidate',
       count(*) FILTER (WHERE sensor_id IN (SELECT sensor_id FROM registry_n)), count(*), 1.0, 'BLOCK' FROM curated
UNION ALL SELECT 'Q_TIME', 'curated candidate',
       count(*) FILTER (WHERE event_time_utc <= ingest_time_utc AND ingest_time_utc <= (SELECT as_of FROM params)),
       count(*), 1.0, 'BLOCK' FROM curated
UNION ALL SELECT 'Q_TIMELY', 'curated rows với event<=ingest<=AS_OF',
       count(*) FILTER (WHERE event_time_utc <= ingest_time_utc AND ingest_time_utc <= (SELECT as_of FROM params)
                          AND epoch(ingest_time_utc) - epoch(event_time_utc) <= (SELECT late_s FROM params)),
       count(*) FILTER (WHERE event_time_utc <= ingest_time_utc AND ingest_time_utc <= (SELECT as_of FROM params)),
       0.95, 'BLOCK' FROM curated
UNION ALL SELECT 'Q_REF_AGREE', 'matched reference IDs',
       count(*) FILTER (WHERE agrees), count(*), 0.95, 'BLOCK' FROM ref_match
UNION ALL SELECT 'Q_REF_COVERAGE', 'all 100 reference IDs',
       (SELECT count(*) FROM ref_match), (SELECT count(*) FROM qa_reference), 1.0, 'BLOCK';

CREATE OR REPLACE VIEW metrics_after AS
SELECT 
    rule_id,
    'curated-candidate' AS dataset_id,
    cohort,
    numerator,
    denominator,
    CASE WHEN denominator = 0 THEN NULL ELSE round(cast(numerator AS DOUBLE) / denominator, 4) END AS value,
    threshold,
    severity,
    CASE WHEN denominator = 0 THEN 'NOT_EVALUATED' ELSE 'EVALUATED' END AS status
FROM metrics_after_raw;

CREATE OR REPLACE VIEW all_out AS
SELECT 'curated' AS src, source_object, source_row FROM curated
UNION ALL SELECT 'quarantine', source_object, source_row FROM quarantine
UNION ALL SELECT 'duplicates', source_object, source_row FROM duplicates;

CREATE OR REPLACE VIEW conservation_check AS
SELECT
  (SELECT count(*) FROM typed)                                                             AS raw_n,
  (SELECT count(*) FROM all_out)                                                           AS out_n,
  (SELECT count(*) FROM (SELECT source_object, source_row FROM typed
                         EXCEPT SELECT source_object, source_row FROM all_out))            AS lost_n,
  (SELECT count(*) FROM (SELECT source_object, source_row FROM all_out
                         EXCEPT SELECT source_object, source_row FROM typed))              AS invented_n,
  (SELECT count(*) FROM (SELECT source_object, source_row FROM all_out
                         GROUP BY 1,2 HAVING count(*) > 1))                                AS overlap_or_dup_n,
  (SELECT count(*) - count(DISTINCT record_id) FROM curated)                               AS curated_dup_id_n;
