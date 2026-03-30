# GLP-1 × Urban Health — Portfolio Project Write-Up

## 1. Project Overview

This project builds an end-to-end data pipeline that ingests pharmaceutical and public health data from four US government APIs, transforms it through a layered analytical database, and delivers interactive visualisations via a web dashboard. The central question:

> After FDA approval of GLP-1 receptor agonist drugs (Ozempic, Wegovy, Mounjaro, Zepbound), did US states with greater clinical trial density experience different obesity rate trajectories?

The pipeline processes **14,000+ records** from OpenFDA, ClinicalTrials.gov, CDC BRFSS, and the US Census Bureau, joins them into a correlation-ready analytical layer in DuckDB, and surfaces the results in a four-tab Streamlit dashboard — all executable with a single command.

---

## 2. Why This Project?

I chose this topic because it sits at the intersection of two domains I know well.

From 2024 to 2025, I worked as a project manager on a GLP-1 pharmaceutical commercialisation project at the National Science and Technology Council (NSTC) in Taiwan. I spent months immersed in GLP-1 receptor agonist market dynamics, regulatory pathways, and clinical data. When I decided to build a data engineering portfolio, I wanted a project that was grounded in real domain knowledge — not a generic Kaggle exercise.

The pharma × urban health angle makes this project stand out for three reasons:

1. **Domain depth.** I can explain why Wegovy's 2021 approval matters, why semaglutide and tirzepatide are different molecules, and why trial density is a meaningful proxy for drug accessibility. Interviewers notice when the person behind the pipeline actually understands the data.

2. **Real-world messiness.** Government APIs are inconsistent — OpenFDA returns dates in `YYYYMMDD` format, ClinicalTrials.gov nests locations three levels deep in JSON, the CDC uses Socrata query syntax, and the Census API occasionally drops SSL connections. This is the kind of data integration challenge that defines real data engineering work.

3. **Genuine analytical value.** The result is not a toy dashboard. The correlation between trial density and obesity slope change (Pearson r = −0.33, p = 0.02) is a real, statistically significant finding that invites further investigation.

---

## 3. What I Learned This From

The technical foundation for this project comes from two structured programmes:

**IBM Data Engineering Professional Certificate** — This is where I learned the principles of ETL pipeline design, data warehouse layering (staging → mart), SQL-based transformations, and database schema design. The staging/mart pattern used in this project's DuckDB schema (`stg_` tables for cleaned raw data, `mart_` tables for analytical outputs) directly applies the dimensional modelling concepts taught in this certificate.

**Harvard CS50 (via edX)** — CS50 gave me the programming fundamentals and problem-solving framework that underpin the Python code in this project: writing modular functions, handling errors gracefully, structuring a project into logical components, and thinking about edge cases. The discipline of writing clean, testable code — treating each ingestion client as a self-contained module with a clear interface (`fetch_*()` → `save_raw()`) — comes from the habits CS50 instills.

This project is where those two learning paths converge into applied practice.

---

## 4. Architecture & Design Decisions

### End-to-End Flow

```
  ┌────────────────────────────────────────────────────────┐
  │                  DATA SOURCES                          │
  │  OpenFDA    ClinicalTrials.gov    CDC BRFSS    Census  │
  └──────────────────────┬─────────────────────────────────┘
                         │  Python (httpx / urllib)
  ┌──────────────────────▼─────────────────────────────────┐
  │                  RAW LAYER                              │
  │             data/raw/*.parquet                          │
  └──────────────────────┬─────────────────────────────────┘
                         │  DuckDB read_parquet()
  ┌──────────────────────▼─────────────────────────────────┐
  │               STAGING LAYER (DuckDB)                    │
  │  stg_fda_approvals    stg_clinical_trials               │
  │  stg_obesity_rates    stg_demographics                  │
  └──────────────────────┬─────────────────────────────────┘
                         │  SQL transforms (JOIN, CTE, REGR_SLOPE)
  ┌──────────────────────▼─────────────────────────────────┐
  │                 MART LAYER (DuckDB)                     │
  │  mart_glp1_timeline     mart_state_obesity              │
  │  mart_trial_density     mart_correlation                │
  └──────────────────────┬─────────────────────────────────┘
                         │  DuckDB Python API
  ┌──────────────────────▼─────────────────────────────────┐
  │             STREAMLIT DASHBOARD                         │
  │  Timeline │ Choropleth │ Correlation │ Trial Map        │
  └────────────────────────────────────────────────────────┘
```

### Why DuckDB (not PostgreSQL or BigQuery)?

I deliberately chose DuckDB for this portfolio project. The reasoning:

| Factor | DuckDB | PostgreSQL | BigQuery |
|--------|--------|------------|----------|
| Setup friction | Zero — a single file, no server | Requires running a daemon | Requires GCP account + billing |
| Parquet support | Native `read_parquet()` | Needs foreign data wrapper | Native but cloud-only |
| Analytical SQL | Excellent (`REGR_SLOPE`, window functions) | Good | Excellent |
| Portability | The `.duckdb` file IS the database | Server-dependent | Cloud-locked |
| Reviewability | Anyone can clone the repo and run it | Must spin up a database | Must have GCP access |

For a portfolio project, **zero-friction reproducibility** matters more than production scale. A hiring manager can `git clone`, `pip install`, run the pipeline, and see the dashboard in under five minutes — with no infrastructure to provision.

That said, I understand the trade-off: in a production environment, I would use PostgreSQL or a cloud warehouse for durability, concurrent access, and integration with orchestration tools like Airflow.

### Why Parquet as the Raw Layer?

Raw API responses are persisted as Parquet files (not CSV, not JSON) because:

- **Columnar format** — DuckDB reads Parquet natively and efficiently; no CSV parsing overhead.
- **Type preservation** — Dates stay as dates, integers stay as integers. No type-inference surprises.
- **Compression** — Parquet is significantly smaller than equivalent CSV.
- **Industry standard** — This is the format used in modern data lake architectures (S3 + Athena, Databricks, Snowflake external tables).

### Why Staging → Mart (not flat tables)?

The two-layer pattern is borrowed from analytics engineering (dbt-style modelling):

- **Staging (`stg_`)** tables are 1:1 with raw sources. They handle column renaming, type casting, and basic filtering — but no business logic.
- **Mart (`mart_`)** tables encode the analytical logic: joins across sources, aggregations, computed metrics like `REGR_SLOPE`. These are the tables the dashboard queries.

This separation means if a source API changes its schema, I only need to update the staging layer. The mart logic stays stable. It also makes the SQL self-documenting — anyone can read `schema.sql` and understand the transformation lineage.

---

## 5. Data Ingestion — The Hard Part

The ingestion layer is where most of the engineering effort went. Four APIs, four different contracts, four different failure modes.

### OpenFDA (`fda_client.py`)

The OpenFDA API returns drug approval records as nested JSON. I query by generic name (semaglutide, tirzepatide, etc.) and extract original submissions (type `ORIG`) to get first-approval dates.

The challenge: OpenFDA's data is incomplete for some drugs. To ensure the timeline is accurate, I maintain a **curated milestones table** of 9 key GLP-1 approvals with verified dates and indications, then merge it with the API results. This "seed + enrich" pattern ensures the pipeline always produces a usable timeline even if the API returns partial data.

### ClinicalTrials.gov (`clinicaltrials.py`)

ClinicalTrials.gov v2 API returns deeply nested JSON. Each study has a `protocolSection` containing `identificationModule`, `statusModule`, `designModule`, and `contactsLocationsModule` — locations are buried three levels deep.

The biggest challenge was a **403 Forbidden error** when using `httpx` with complex query parameters containing geo-filters. The root cause was URL encoding — `httpx` encoded the parentheses in `distance(39.8,-98.6,3000km)` differently from what the server expected.

My solution: a **fallback strategy**. The primary fetcher uses `httpx`. If it gets a 403, it switches to a `urllib`-based fallback that queries each drug × condition pair separately (simpler URLs, no encoding issues), then deduplicates by NCT ID. This produced 1,360 unique trials from 1,681 raw results.

```python
if resp.status_code == 403:
    print("  INFO: ClinicalTrials.gov returned 403 — trying urllib fallback...")
    return _fetch_trials_urllib(max_pages)
```

I also **flattened the nested JSON** into one row per trial-location pair (12,766 rows from 1,360 trials), because the analytical question is about geographic distribution — I need state-level granularity.

### CDC BRFSS (`cdc_brfss.py`)

The CDC exposes BRFSS data through a Socrata API. The key decisions:

- Filter to `question = 'Percent of adults aged 18 years and older who have obesity'` to get the right indicator.
- Keep only `stratification = 'Total'` (unstratified) rows — subgroup analysis is out of scope.
- Drop US territories (Guam, Puerto Rico, etc.) for consistency with the 50-state analysis.
- Cast types explicitly — Socrata returns everything as strings.

### US Census ACS (`census_client.py`)

The Census API was the most unreliable source. During development, it consistently failed with SSL handshake errors (`UNEXPECTED_EOF_WHILE_READING`), likely due to server-side TLS configuration issues.

My solution: a **seed data fallback**. If the API is unreachable, the client generates approximate ACS values based on published estimates (median income by state, insurance coverage trends). The seed data is clearly marked in logs and documentation. In production, I would replace this with a cached download or a more robust HTTP client with retry logic.

```python
df = fetch_all_years(api_key)
if df.empty:
    print("  INFO: Census API unreachable — using seed data for demonstration")
    df = generate_seed_data()
```

### Pipeline Resilience

The pipeline runner (`run_pipeline.py`) wraps each ingestion step in a try/except block. If one source fails, the pipeline continues with the remaining sources. This is a deliberate design choice — partial data is better than no data, and the DuckDB schema handles missing tables gracefully.

```python
for step, label, module_path in sources:
    try:
        mod = __import__(module_path, fromlist=["save_raw"])
        mod.save_raw()
    except Exception as e:
        print(f"  ERROR: {label} failed — {e}")
        print(f"  Continuing with remaining sources...")
```

---

## 6. Data Modelling

### The Schema (`schema.sql`)

The entire transformation logic lives in a single SQL file — 137 lines that define 9 tables. This is intentional: SQL is the most readable way to express data transformations, and having everything in one file makes the lineage obvious.

**Staging layer** (4 tables) — direct loads from Parquet with no logic:

```sql
CREATE OR REPLACE TABLE stg_fda_approvals AS
SELECT * FROM read_parquet('data/raw/fda_glp1_approvals.parquet');
```

**Dimension table** (1 table) — a state abbreviation lookup derived from CDC data:

```sql
CREATE OR REPLACE TABLE dim_states AS
SELECT DISTINCT state_abbr, state_name
FROM stg_obesity_rates
WHERE state_abbr NOT IN ('US', 'DC');
```

**Mart layer** (4 tables) — the analytical models:

- `mart_glp1_timeline` — Filtered to curated milestones with known indications.
- `mart_state_obesity` — Joins obesity rates with Census demographics by state + year.
- `mart_trial_density` — Aggregates trial counts, completion status, and date ranges by state.
- `mart_correlation` — The centrepiece. Uses CTEs to compute pre/post Wegovy (2021) obesity rate slopes via `REGR_SLOPE()`, then joins with trial density and demographics.

### The State Name Problem

A real-world data integration issue: ClinicalTrials.gov uses full state names ("California"), CDC uses abbreviations ("CA"), and both exist in the Census data. I solved this with a `dim_states` lookup table derived from CDC data (which has both fields), then joined other sources through it. This is the kind of mundane but essential data engineering that makes or breaks a pipeline.

### The Correlation Model

The most complex SQL is `mart_correlation`, which uses four CTEs:

1. **`pre_slope`** — Linear regression slope of obesity % vs. year (2016–2020) per state.
2. **`post_slope`** — Same for 2021–2023 (post-Wegovy approval).
3. **`trial_density`** — Trial count per state, joined through `dim_states`.
4. **`demographics`** — Average income and insurance rate (2018–2022) as control variables.

The final `slope_change` column (post − pre) captures whether a state's obesity trend accelerated or decelerated after GLP-1 drugs became available for weight management.

```sql
REGR_SLOPE(obesity_pct, year) AS pre_slope
```

I used DuckDB's built-in `REGR_SLOPE()` aggregate function rather than computing it in Python — keeping the logic in SQL means it's declarative, reproducible, and auditable.

---

## 7. Analysis & Statistical Rigour

### Why Slope Change, Not Before/After Averages?

A naive approach would compare average obesity rates before and after 2021. But obesity rates were already rising before GLP-1 drugs — so even a state with rising obesity could show improvement if the rate of increase slowed down.

By computing the **linear regression slope** in each period, I capture the **trend direction and rate**, not just the level. The `slope_change` metric (post-slope minus pre-slope) tells us whether the trajectory shifted — which is far more informative.

### Why Both Pearson and Spearman?

- **Pearson** assumes a linear relationship and is sensitive to outliers. It measures the strength of the linear association.
- **Spearman** is rank-based and makes no linearity assumption. It captures monotonic relationships even if the relationship is non-linear.

Both are reported for every variable pair because a hiring manager or reviewer who understands statistics will expect to see both. It demonstrates awareness that correlation metrics have assumptions.

### The Ecological Fallacy Disclaimer

I explicitly note throughout the project — in the README, in the dashboard, and in the analysis output — that this is an **ecological correlation study**. State-level associations do not imply individual-level causation. A state with more trials may have better obesity outcomes for many reasons unrelated to GLP-1 drugs (better healthcare infrastructure, higher income, different demographics).

This is not just academic caution. In a professional setting, presenting ecological correlations as causal claims is a credibility-destroying mistake. Being upfront about limitations is itself a signal of analytical maturity.

### Key Results

| Variable Pair | Pearson r | p-value | Interpretation |
|---------------|-----------|---------|----------------|
| Trial density vs. slope change | −0.33 | 0.02 | States with more trials had better trend improvement |
| Income vs. slope change | +0.25 | 0.08 | Wealthier states had slightly worse trends (borderline) |
| Insurance rate vs. slope change | −0.21 | 0.15 | Not statistically significant |

---

## 8. Dashboard as the Delivery Layer

The Streamlit dashboard has four tabs, each designed to answer a specific question:

| Tab | Question | Visualisation |
|-----|----------|---------------|
| GLP-1 Approval Timeline | When were key drugs approved, and how does national obesity track? | Line chart + event markers (Plotly) |
| State Obesity Map | How does obesity vary geographically, and how has it changed? | Animated choropleth with year slider |
| Correlation Analysis | Is trial density associated with obesity trend changes? | Scatter plot with OLS trendline + metrics |
| Clinical Trial Map | Where are GLP-1 trials concentrated? | Choropleth + horizontal bar chart |

I chose **Streamlit + Plotly** over alternatives (Dash, Grafana, Metabase) because:

- Streamlit is pure Python — no frontend code, no JavaScript, no separate server.
- Plotly's choropleth maps handle US state-level data out of the box.
- The combination is the fastest path from DuckDB query to interactive chart.
- It deploys to Streamlit Cloud with zero configuration.

---

## 9. Testing & Reproducibility

### What I Tested

I wrote 9 tests in two categories:

**Data structure tests** (`test_fda_client.py`) — Verify the curated milestones table has the right columns, correct data types, is sorted chronologically, and contains all key drugs (Ozempic, Wegovy, Mounjaro, Zepbound). These tests run without any API calls.

**Data integrity tests** (`test_transforms.py`) — Verify the DuckDB database has all expected staging and mart tables, that the obesity data covers at least 49 states, that the correlation table has sufficient rows, and that all expected columns exist. These tests require a built database.

I intentionally focused on **data validation** rather than function-level unit tests. In data engineering, the most common failures are not code bugs — they are schema changes, missing values, wrong data types, and broken joins. Testing the data itself catches these.

### Environment Management: Conda over `.venv/`

I chose **Conda** (via Anaconda) over per-project `.venv/` virtual environments for a practical reason: disk space. Each `.venv/` duplicates the full dependency tree (~400 MB for this project). With multiple data projects, that adds up fast. Conda manages environments centrally in a shared `envs/` directory, so common packages (numpy, pandas) are stored once and reused.

```bash
conda create -n glp1-dashboard python=3.11 -y
conda activate glp1-dashboard
pip install -e ".[dev]"
```

This gives the same isolation as `.venv/` — the project's dependencies don't contaminate other projects — without duplicating hundreds of megabytes per project. In VSCode, selecting the `glp1-dashboard` conda interpreter (`Cmd+Shift+P` → Python: Select Interpreter) makes the integrated terminal activate the environment automatically.

For reviewers who don't use Conda, the project also ships with a Dockerfile (see Section 10) — zero local installation required.

### One-Command Reproducibility

```bash
python pipelines/run_pipeline.py
```

This single command runs the full pipeline: ingests from all four APIs, persists raw Parquet files, builds the DuckDB staging and mart layers, and runs the correlation analysis. The pipeline is idempotent — running it again overwrites the previous results cleanly.

The project also follows production habits:
- `pyproject.toml` — Dependency management with pinned versions.
- `.env.example` — Documents required environment variables without exposing secrets.
- `.gitignore` — Excludes `data/raw/`, `.duckdb` files, and virtual environments from version control.

---

## 10. Docker Containerisation

### Why Containerise a Portfolio Project?

A common problem with data projects: "It works on my machine." Different Python versions, different OS-level libraries, different dependency resolutions — any of these can break a pipeline silently. Docker eliminates this by packaging the entire runtime environment into an image that behaves identically everywhere.

For this project specifically, containerisation solves three problems:

1. **Reviewer convenience.** A hiring manager can run the dashboard without installing Python, DuckDB, or any dependencies — just `docker run`.
2. **Deployment readiness.** The same image runs locally, on AWS ECS, on Google Cloud Run, or on any Kubernetes cluster. Containerisation is the standard packaging format for production data services.
3. **Environment lock.** The Python version (3.11), the OS (Debian slim), and every dependency are pinned in the image. No "it worked last week" surprises.

### Multi-Stage Build

I used a **multi-stage Dockerfile** — a pattern that separates the build environment from the runtime environment:

```dockerfile
# Stage 1: Builder — has compilers, builds wheels
FROM python:3.11-slim AS builder
# ... install build-essential, pip install all dependencies

# Stage 2: Runtime — only what's needed to run the app
FROM python:3.11-slim
COPY --from=builder /opt/venv /opt/venv
COPY src/ dashboard/ pipelines/ data/ .
CMD ["streamlit", "run", "dashboard/app.py", ...]
```

Why this matters:

| | Single-stage | Multi-stage |
|---|---|---|
| Image size | ~800 MB (includes gcc, build headers) | ~250 MB (runtime only) |
| Attack surface | Larger (compilers in production) | Smaller (no build tools) |
| Build time | Same | Same (builds once, copies result) |

The builder stage installs `build-essential` (needed to compile C extensions for packages like `scipy` and `pyarrow`), builds all Python wheels, then the runtime stage copies only the finished virtual environment. The compilers never make it into the final image.

### How It Works

```bash
# Build the image
docker build -t glp1-dashboard .

# Run the pipeline (ingest data + build DuckDB)
docker run glp1-dashboard python pipelines/run_pipeline.py

# Launch the dashboard (accessible at http://localhost:8501)
docker run -p 8501:8501 glp1-dashboard
```

The `-p 8501:8501` flag maps the container's port to the host — Streamlit serves inside the container, but the browser connects from outside. Without this flag, the dashboard runs but is invisible to the host network.

### .dockerignore

Just as `.gitignore` keeps unwanted files out of version control, `.dockerignore` keeps them out of the Docker build context. I exclude:

- `.venv/`, `__pycache__/` — local development artefacts
- `data/raw/`, `*.duckdb` — generated by the pipeline, not source code
- `.env` — secrets must never be baked into images
- `.git/` — build context should be small and fast to transfer

### Health Check

The Dockerfile includes a health check that pings Streamlit's internal health endpoint every 30 seconds:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
```

This is not just a nice-to-have. In production orchestrators (Kubernetes, ECS, Docker Swarm), health checks determine whether a container is alive or needs to be restarted. Including one shows awareness of how containers are managed in real deployment environments.

---

## 11. What I Would Do Differently With More Time

This project was built as a portfolio demonstration. In a production environment, I would add:

- **Orchestration** — Airflow or Prefect DAGs instead of a single Python script, with dependency management between ingestion and transformation steps, scheduling, and alerting on failure.
- **dbt** — Replace the raw SQL schema with dbt models for version-controlled transformations, automated documentation, and data lineage tracking.
- **Incremental loads** — Currently the pipeline does full refreshes. With real CDC/Census data (updated annually), incremental processing would avoid re-fetching unchanged records.
- **Data quality framework** — Great Expectations or dbt tests for automated data contract enforcement (e.g., obesity percentages must be between 0 and 100, no null state abbreviations).
- **CI/CD** — GitHub Actions to run tests on every push and deploy the dashboard automatically.

These are the tools I would reach for on a team. For a portfolio project, the priority was demonstrating that I understand the patterns — layered architecture, resilient ingestion, SQL-based transformation, statistical analysis, containerised delivery, and interactive visualisation — without over-engineering the infrastructure.
