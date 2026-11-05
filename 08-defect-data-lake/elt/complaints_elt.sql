-- ELT: the raw data is already loaded in S3; transform it with SQL, inside Athena.
-- CREATE TABLE AS SELECT (CTAS) runs the SELECT and writes the result as new Parquet files,
-- partitioned by received year, and registers them as a table in the Glue catalog.
-- Same cleaning rules as the Spark job in etl/complaints_etl.py.
-- {database} and {bucket} are filled in by pipeline/elt.py.

CREATE TABLE {database}.complaints_elt
WITH (
  format = 'PARQUET',
  write_compression = 'SNAPPY',
  external_location = 's3://{bucket}/curated/elt/complaints/',
  partitioned_by = ARRAY['received_year']  -- must be the LAST column of the SELECT
) AS
WITH cleaned AS (
  SELECT
    try_cast(NULLIF(trim(cmplid), '') AS bigint)                       AS complaint_id,
    try_cast(NULLIF(trim(odino), '') AS bigint)                        AS odi_number,
    NULLIF(trim(mfr_name), '')                                         AS manufacturer,
    upper(NULLIF(trim(maketxt), ''))                                   AS make,
    upper(NULLIF(trim(modeltxt), ''))                                  AS model,
    CASE WHEN try_cast(trim(yeartxt) AS integer) BETWEEN 1900 AND 2100  -- 9999 = unknown
         THEN try_cast(trim(yeartxt) AS integer) END                   AS model_year,
    NULLIF(trim(compdesc), '')                                         AS component,
    NULLIF(trim(split_part(compdesc, ':', 1)), '')                     AS component_group,
    CASE upper(trim(crash)) WHEN 'Y' THEN true WHEN 'N' THEN false END AS crash,
    CASE upper(trim(fire)) WHEN 'Y' THEN true WHEN 'N' THEN false END  AS fire,
    coalesce(try_cast(trim(injured) AS integer), 0)                    AS injured,
    coalesce(try_cast(trim(deaths) AS integer), 0)                     AS deaths,
    CASE upper(trim(medical_attn)) WHEN 'Y' THEN true WHEN 'N' THEN false END      AS medical_attention,
    CASE upper(trim(vehicles_towed_yn)) WHEN 'Y' THEN true WHEN 'N' THEN false END AS towed,
    CASE upper(trim(police_rpt_yn)) WHEN 'Y' THEN true WHEN 'N' THEN false END     AS police_report,
    CASE WHEN try_cast(trim(miles) AS integer) BETWEEN 0 AND 2000000
         THEN try_cast(trim(miles) AS integer) END                     AS miles,
    CASE WHEN try_cast(trim(veh_speed) AS integer) BETWEEN 0 AND 200
         THEN try_cast(trim(veh_speed) AS integer) END                 AS vehicle_speed,
    try(CAST(date_parse(NULLIF(trim(faildate), ''), '%Y%m%d') AS date)) AS failure_date,
    try(CAST(date_parse(NULLIF(trim(ldate), ''), '%Y%m%d') AS date))    AS received_date,
    NULLIF(trim(state), '')                                            AS state,
    NULLIF(trim(cmpl_type), '')                                        AS complaint_type,
    NULLIF(trim(prod_type), '')                                        AS product_type,
    NULLIF(trim(fuel_type), '')                                        AS fuel_type,
    NULLIF(trim(drive_train), '')                                      AS drive_train,
    NULLIF(trim(cdescr), '')                                           AS description
  FROM {database}.complaints_raw
)
SELECT *, year(received_date) AS received_year
FROM cleaned
WHERE complaint_id IS NOT NULL AND received_date IS NOT NULL
