-- curate.sql  (T3, role C)  research-telemetry-v1
CREATE OR REPLACE TABLE registry_norm AS
SELECT upper(trim(sensor_id)) AS sensor_id, any_value(site) AS site, count(*) AS n
FROM registry GROUP BY 1;

CREATE OR REPLACE TABLE stage1 AS
SELECT t.*,
  list_filter([
    CASE WHEN NOT COALESCE(t.parse_ok, false) THEN 'PARSE' END,
    CASE WHEN NOT COALESCE(regexp_full_match(t.record_id, p.id_pattern), false) THEN 'KEY' END,
    CASE WHEN t.ingest_ts IS NULL THEN 'INGEST_PARSE' END
  ], x -> x IS NOT NULL) AS pre_reasons
FROM typed t CROSS JOIN params p;

CREATE OR REPLACE TABLE ranked AS
SELECT *,
  ROW_NUMBER() OVER (
    PARTITION BY record_id
    ORDER BY ingest_ts DESC, source_object ASC, source_row ASC) AS rn
FROM stage1
WHERE len(pre_reasons) = 0;

CREATE OR REPLACE TABLE winners_eval AS
WITH w AS (
  SELECT r.*, g.site AS site_reg,
    CASE r.unit WHEN 'C' THEN r.value_num
                WHEN 'F' THEN (r.value_num - 32.0) * 5.0 / 9.0 END AS temp_c
  FROM ranked r LEFT JOIN registry_norm g ON g.sensor_id = r.sensor_id
  WHERE r.rn = 1
)
SELECT w.*,
  list_filter([
    CASE WHEN COALESCE(w.record_id,'')='' OR COALESCE(w.sensor_id,'')=''
           OR COALESCE(trim(w.event_time),'')='' OR COALESCE(trim(w.ingest_time),'')=''
           OR COALESCE(trim(w.reading),'')='' OR COALESCE(w.unit,'')=''
         THEN 'REQUIRED' END,
    CASE WHEN NOT COALESCE(isfinite(w.value_num), false) THEN 'NUMERIC' END,
    CASE WHEN NOT COALESCE(w.unit IN ('C','F'), false) THEN 'UNIT' END,
    CASE WHEN NOT COALESCE(w.temp_c BETWEEN p.min_c AND p.max_c, false) THEN 'RANGE' END,
    CASE WHEN w.event_ts IS NULL THEN 'TIME_PARSE' END,
    CASE WHEN NOT COALESCE(w.event_ts <= w.ingest_ts AND w.ingest_ts <= p.as_of, false)
         THEN 'TIME_ORDER' END,
    CASE WHEN w.site_reg IS NULL THEN 'REFERENCE' END
  ], x -> x IS NOT NULL) AS reasons
FROM w CROSS JOIN params p;

CREATE OR REPLACE TABLE curated_out AS
SELECT w.record_id, w.sensor_id, w.site_reg AS site,
  w.event_ts AS event_time_utc, w.ingest_ts AS ingest_time_utc,
  CAST(round(w.temp_c, 2) AS DECIMAL(8,2)) AS temperature_c,
  (date_diff('second', w.event_ts, w.ingest_ts) > p.late_s) AS is_late,
  w.source_object, w.source_row, w.source_sha256
FROM winners_eval w CROSS JOIN params p
WHERE len(w.reasons) = 0;

CREATE OR REPLACE TABLE quarantine_out AS
SELECT source_object, source_row, source_sha256, record_id,
  'PRE_KEY' AS stage, pre_reasons[1] AS primary_reason,
  array_to_string(pre_reasons, '|') AS all_reasons, raw_payload
FROM stage1 WHERE len(pre_reasons) > 0
UNION ALL
SELECT source_object, source_row, source_sha256, record_id,
  'WINNER_VALIDATION', reasons[1], array_to_string(reasons, '|'), raw_payload
FROM winners_eval WHERE len(reasons) > 0;

CREATE OR REPLACE TABLE duplicates_out AS
SELECT r.source_object, r.source_row, r.source_sha256, r.record_id,
  'SUPERSEDED' AS reason,
  w.source_object AS winner_source_object, w.source_row AS winner_source_row
FROM ranked r JOIN ranked w ON w.record_id = r.record_id AND w.rn = 1
WHERE r.rn > 1;
