-- DuckDB schema for GLP-1 × Urban Health analysis
-- Layers: stg_ (staging / cleaned) → mart_ (analytical)

-------------------------------------------------------
-- STAGING LAYER
-------------------------------------------------------

CREATE OR REPLACE TABLE stg_fda_approvals AS
SELECT * FROM read_parquet('data/raw/fda_glp1_approvals.parquet');

CREATE OR REPLACE TABLE stg_clinical_trials AS
SELECT * FROM read_parquet('data/raw/clinicaltrials_glp1.parquet');

CREATE OR REPLACE TABLE stg_obesity_rates AS
SELECT * FROM read_parquet('data/raw/cdc_obesity_rates.parquet');

CREATE OR REPLACE TABLE stg_demographics AS
SELECT * FROM read_parquet('data/raw/census_acs_demographics.parquet');

-------------------------------------------------------
-- STATE ABBREVIATION LOOKUP
-------------------------------------------------------

CREATE OR REPLACE TABLE dim_states AS
SELECT DISTINCT state_abbr, state_name
FROM stg_obesity_rates
WHERE state_abbr IS NOT NULL
  AND state_abbr NOT IN ('US', 'DC');

-------------------------------------------------------
-- MART LAYER
-------------------------------------------------------

-- Mart 1: GLP-1 approval timeline (key milestones only, deduplicated)
CREATE OR REPLACE TABLE mart_glp1_timeline AS
SELECT
    brand_name,
    generic_name,
    approval_date,
    indication,
    EXTRACT(YEAR FROM approval_date) AS approval_year
FROM stg_fda_approvals
WHERE indication IS NOT NULL
  AND approval_date IS NOT NULL
ORDER BY approval_date;

-- Mart 2: State-level obesity trend with demographics
CREATE OR REPLACE TABLE mart_state_obesity AS
SELECT
    o.year,
    o.state_abbr,
    o.state_name,
    o.obesity_pct,
    o.sample_size,
    d.median_income,
    d.insurance_rate
FROM stg_obesity_rates o
LEFT JOIN stg_demographics d
    ON o.state_name = d.state_name
    AND o.year = d.year
WHERE o.state_abbr NOT IN ('US', 'DC')
ORDER BY o.state_abbr, o.year;

-- Mart 3: Clinical trial density by state
CREATE OR REPLACE TABLE mart_trial_density AS
SELECT
    state,
    COUNT(DISTINCT nct_id) AS trial_count,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_trials,
    SUM(CASE WHEN status = 'RECRUITING' THEN 1 ELSE 0 END) AS recruiting_trials,
    MIN(start_date) AS earliest_trial,
    MAX(start_date) AS latest_trial
FROM stg_clinical_trials
WHERE state != ''
GROUP BY state
ORDER BY trial_count DESC;

-- Mart 4: Combined correlation-ready table
-- Joins obesity trend slope (pre/post Wegovy 2021) with trial density
CREATE OR REPLACE TABLE mart_correlation AS
WITH pre_slope AS (
    SELECT
        state_abbr,
        REGR_SLOPE(obesity_pct, year) AS pre_slope,
        AVG(obesity_pct) AS pre_avg_obesity
    FROM stg_obesity_rates
    WHERE year BETWEEN 2016 AND 2020
      AND state_abbr NOT IN ('US', 'DC')
      AND obesity_pct IS NOT NULL
    GROUP BY state_abbr
),
post_slope AS (
    SELECT
        state_abbr,
        REGR_SLOPE(obesity_pct, year) AS post_slope,
        AVG(obesity_pct) AS post_avg_obesity
    FROM stg_obesity_rates
    WHERE year BETWEEN 2021 AND 2023
      AND state_abbr NOT IN ('US', 'DC')
      AND obesity_pct IS NOT NULL
    GROUP BY state_abbr
),
trial_density AS (
    SELECT
        s.state_abbr,
        COALESCE(t.trial_count, 0) AS trial_count
    FROM dim_states s
    LEFT JOIN mart_trial_density t
        ON s.state_name = t.state
),
demographics AS (
    SELECT
        state_name,
        AVG(median_income) AS avg_median_income,
        AVG(insurance_rate) AS avg_insurance_rate
    FROM stg_demographics
    WHERE year BETWEEN 2018 AND 2022
    GROUP BY state_name
)
SELECT
    pre.state_abbr,
    ds.state_name,
    pre.pre_slope,
    pre.pre_avg_obesity,
    post.post_slope,
    post.post_avg_obesity,
    (post.post_slope - pre.pre_slope) AS slope_change,
    td.trial_count,
    dem.avg_median_income,
    dem.avg_insurance_rate
FROM pre_slope pre
JOIN post_slope post USING (state_abbr)
JOIN dim_states ds USING (state_abbr)
LEFT JOIN trial_density td USING (state_abbr)
LEFT JOIN demographics dem ON ds.state_name = dem.state_name
ORDER BY pre.state_abbr;
