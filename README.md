# NYC Car Incidents Data Engineering Pipeline

## Project Overview
An end-to-end data engineering portfolio project that ingests, stores, transforms, orchestrates, and visualizes NYC motor vehicle collision data. Built to demonstrate hands-on, job-market-relevant skills across the modern data stack.

**Goal:** Showcase practical experience with cloud storage, APIs, SQL, Python, data warehousing, orchestration, data quality/management, and dashboarding — suitable for a data engineering resume/portfolio.

---

## Data Source
**NYC Open Data — Motor Vehicle Collisions**, accessed via the Socrata Open Data API (SODA), free with an app token.

Three related tables are ingested to support a relational, multi-table warehouse model (rather than a single flat table):
- **Crashes** — one row per collision event
- **Vehicles** — one or more vehicles involved per crash
- **Person** — one or more people involved per crash (drivers, passengers, pedestrians, cyclists)

This 1-to-many relational structure supports realistic dbt modeling (staging → intermediate → marts) and meaningful joins.

---

## Architecture / Stack

| Layer | Tool | Notes |
|---|---|---|
| Ingestion | **Python** + Socrata API (SODA) | Pulls Crashes, Vehicles, Person tables |
| Raw Storage | **AWS S3** | Landing zone for raw JSON/CSV extracts |
| Warehouse / Query Engine | **AWS Athena** | Serverless SQL over S3 data |
| Transformation | **dbt Cloud** | Staging, intermediate, and mart models; built-in testing |
| Orchestration | **Apache Airflow** (Docker, via WSL2) | Schedules ingestion, triggers dbt Cloud jobs via API |
| Dashboard | **Looker Studio** | Native Athena connector; free, shareable public link |
| Version Control | **Git / GitHub** | All pipeline code |

### Why AWS?
Chosen over GCP/Azure specifically for stronger, more frequent presence in data engineering job postings — this project is being built with hiring signal in mind, not just technical convenience.

### Why dbt Cloud (not dbt Core)?
Avoids local dbt installs/versioning conflicts inside an already Docker+WSL2-heavy environment; provides a browser IDE; dbt Cloud jobs are triggered via its API from Airflow (a common real-world orchestration pattern) rather than relying on dbt Cloud's native scheduler.

### Why Looker Studio (not Tableau/Power BI)?
Native Athena connector with no licensing friction, genuinely free, and produces a shareable public dashboard link — ideal for a portfolio piece. (Power BI/Tableau are more commonly requested in job postings but have more awkward/limited Athena connectivity on their free tiers.)

### Data Modeling Approach (dbt layers)
- **Staging** (`stg_crashes`, `stg_vehicles`, `stg_person`): light cleanup of raw source tables — renaming, type casting, standardization. No joins/business logic.
- **Intermediate** (`int_`): joins/reshaping stepping stones (e.g., vehicle counts per crash, person injury classification).
- **Marts — Star Schema (core)**: `fct_crashes` (fact table) + `dim_vehicles`, `dim_persons` (dimension tables). This is the primary, resume-relevant dimensional model.
- **Marts — BI layer (on top of star schema)**: `fct_crash_details` — a single flattened, denormalized table pre-joining fact + dims, built specifically for Looker Studio to query directly (simpler for BI tool consumption, common real-world pattern).

### How Incremental Ingestion Works
Rather than re-downloading millions of rows on every run, the ingestion script can pull **only records that are new or have changed** since the last successful run. Here's the mechanism, end to end:

1. **Socrata tracks changes automatically.** Every row in a Socrata dataset carries a hidden system field, `:updated_at`, which gets set the moment a record is created *or* later amended (NYC crash reports are sometimes revised after the fact). This field can be queried directly: `$where=:updated_at > '<timestamp>'`.
2. **A "high-water mark" is stored per table, in S3 — not on the laptop.** After each successful run, the script writes the current timestamp into a small JSON file at `s3://nyc-collisions-gustavo-raw/pipeline-state/last_run.json`, one entry per table. Storing this in S3 (rather than as a local file) matters because Step 7's Airflow DAG will eventually run this script inside Docker containers, which don't reliably persist local disk state between runs — S3 does.
3. **Each incremental run reads that file first**, then asks Socrata only for rows changed after each table's stored timestamp — turning a multi-million-row full pull into a query that, most days, returns only a handful of rows (or zero, if nothing changed).
4. **A new, small, timestamped file is uploaded to S3** alongside the existing full-data file for that table — the pipeline never overwrites prior files, it only adds to them.
5. **Amended records are handled downstream, not at ingestion.** If NYPD revises an existing crash report, that `collision_id` will legitimately appear again in a later incremental file with updated values — meaning multiple versions of the same ID can exist across different S3 files. This is by design. Deduplication (keeping only the latest version of each ID) happens in dbt's staging layer (Step 6), typically via `ROW_NUMBER() OVER (PARTITION BY id ORDER BY ingested_at DESC)`.

**Two supporting script flags:**
- `--seed-state` — writes "now" as the baseline for all tables, without fetching any data. Used once, right after an existing full pull, so the very first `--incremental` run doesn't mistake "no prior state" for "first run ever" and accidentally re-pull everything.
- `--incremental` — the actual incremental run, using whatever state currently exists.

**Current status:** implemented and tested successfully — correctly returns 0 changed records for all three tables, consistent with NYC Open Data's own notice that this dataset's automated updates are temporarily paused (expected fix: August 2026). The logic is ready to pick up real changes automatically once the source resumes updating.

### Why dbt built-in tests (not Great Expectations)?
dbt's generic tests (`not_null`, `unique`, `relationships`, `accepted_values`) run automatically as part of the dbt Cloud job and give solid coverage — missing values, duplicate crash IDs, orphaned vehicle/person records, invalid categorical values — without adding a separate Python framework to configure and maintain. Great Expectations remains a natural "v2" enhancement once the core pipeline is stable.

### Local Environment
- Windows laptop, 16 GB RAM
- Docker Desktop via WSL2 (confirmed feasible for running Airflow's containers at this RAM level)
- Local project path: `D:\Projects\nyc-collisions-data-engineering`

### AWS Setup (Summary)
- AWS account created (Paid plan, not the 6-month auto-closing Free plan), region standardized on **us-east-1 (N. Virginia)**.
- Root account secured with MFA; billing alerts and a budget configured as a safety net.
- IAM user `data-eng-user` created for all daily work (root reserved for account-level tasks only).
- S3 bucket **`nyc-collisions-gustavo-raw`** created in `us-east-1` with `crashes/`, `vehicles/`, `person/`, and `athena-query-results/` folders.
- Athena configured: query result location set to the S3 bucket's `athena-query-results/` folder; dedicated database **`nyc_collisions`** created via SQL and set as active.
- Full step-by-step walkthrough: [`docs/aws-setup.md`](./docs/aws-setup.md)

### Version Control Setup (Summary)
- GitHub account created; repo `nyc-collisions-data-engineering` (public) will host all project code.
- Git for Windows + GitHub CLI (`gh`) installed locally; authenticated via `gh auth login` (browser-based, no passwords).
- Local repo initialized with a clean folder structure: `dags/` (Airflow), `dbt/` (dbt Cloud project), `ingestion/` (Python scripts), `docs/` (documentation).
- Full step-by-step walkthrough, including a Windows Command Prompt gotcha (multi-line paste issue) and the fix, documented in [`docs/git-setup.md`](./docs/git-setup.md).
- Quick reference of every Git/GitHub CLI command used, with explanations: [`docs/git-commands-reference.md`](./docs/git-commands-reference.md)

### Python Ingestion Setup (Summary)
- Python 3.14.7 installed from python.org (not the Microsoft Store placeholder); VS Code used as the editor with the Python extension.
- Project-scoped virtual environment (`venv`) with `requests`, `boto3`, `python-dotenv` installed; versions locked in `ingestion/requirements.txt`.
- Credentials (Socrata API Key ID/Secret, AWS Access Key/Secret) stored in a local `.env` file, excluded from Git.
- `ingestion/ingest.py` pulls Crashes, Vehicles, and Person tables from the Socrata API (paginated), saves raw JSON locally, then uploads to the matching S3 folder.
- **Auth gotcha fixed:** Socrata's current API Key system requires HTTP Basic Auth (Key ID + Secret), not the older `X-App-Token` header — full explanation in the doc below.
- Script supports `--test` (small sample, ~1,000 rows/table) and `--tables <name(s)>` (run specific table(s) only) flags via the same file — no code changes needed to switch modes. **Windows gotcha:** always invoke with the explicit `python` prefix (`python ingestion\ingest.py`) — running `ingest.py` directly can silently drop command-line arguments.
- **Full ingestion complete.** All three tables successfully pulled and uploaded to S3: Crashes (2,269,187 records), Vehicles (4,551,002 records), Person (5,984,110 records).
- **Incremental ingestion designed and tested.** Uses Socrata's `:updated_at` system field with a per-table high-water-mark state file stored in S3 (`pipeline-state/last_run.json`, not local disk — survives across Docker/Airflow runs later). New flags: `--seed-state` (initialize baseline) and `--incremental` (fetch only changed records). Amended records are expected to create duplicate IDs across files by design; deduplication happens downstream in dbt's staging layer, not at ingestion time.
- Full step-by-step walkthrough, including three gotchas encountered (Socrata auth fix, Windows argument-passing issue, SoQL system-field colon syntax) and their fixes: [`docs/ingestion-setup.md`](./docs/ingestion-setup.md)

### Athena Table Setup (Summary)
- Used a hybrid approach: **AWS Glue Crawler** for initial schema discovery + table creation, then manual review — rather than hand-writing DDL for three wide (25–45+ column) tables.
- IAM role `AWSGlueServiceRole-nyc-collisions` created for the crawler; crawler `nyc-collisions-crawler` targets all three S3 folders, registering tables `raw_crashes`, `raw_vehicles`, `raw_person` in the `nyc_collisions` database.
- **Major gotcha found and fixed:** Athena's JSON reader requires NDJSON (one JSON object per line) — the ingestion script was originally writing a single wrapping JSON array per file, which crawled successfully (schema detection) but failed at actual query time (`HIVE_CURSOR_ERROR`). Fixed by updating the ingestion script to write NDJSON, then regenerating all three source files.
- **Validated end-to-end:** row counts in Athena match the ingestion script's own logged counts exactly for all three tables (2,269,187 / 4,551,002 / 5,984,110).
- Full step-by-step walkthrough: [`docs/athena-setup.md`](./docs/athena-setup.md)

### dbt Cloud Setup (Summary)
- Free dbt Cloud account created; project `nyc_collisions` connected to Athena (region `us-east-1`, database `nyc_collisions`, S3 staging directory reusing the existing `athena-query-results/` folder).
- **Three setup gotchas found and fixed:**
  1. dbt Cloud's newer **"Fusion" engine doesn't support Athena** — every environment must be explicitly set to the **"Compatible"** (classic dbt Core) release track instead.
  2. The Development environment silently failed to persist during onboarding (due to the Fusion connection test failing) — had to be created manually.
  3. GitHub repository connection needed an explicit GitHub App install, scoped to just this one repo (least-privilege).
- Connection test succeeded; dbt Cloud Studio confirmed working with the real repo contents visible.
- Ran "Initialize dbt project," scaffolding the standard dbt folder structure (`models/`, `macros/`, `seeds/`, `snapshots/`, `tests/`, `dbt_project.yml`) directly into the connected GitHub repo.
- **Workflow note:** `master` is protected in dbt Cloud Studio — changes are committed to a feature branch first, then merged via GitHub PR (realistic Git practice, carried forward for all dbt work).
- Full step-by-step walkthrough, including all three gotchas: [`docs/dbt-setup.md`](./docs/dbt-setup.md)

---

## Schema Design (Confirmed)

### Staging Layer (1:1 with raw source tables, light cleanup only)

**`stg_crashes`** (grain: one row per crash)
- `collision_id` (PK), `crash_date`, `crash_time`, `borough`, `zip_code`, `latitude`, `longitude`, `on_street_name`, `cross_street_name`, `off_street_name`, `number_of_persons_injured`, `number_of_persons_killed`, `number_of_pedestrians_injured`/`killed`, `number_of_cyclist_injured`/`killed`, `number_of_motorist_injured`/`killed`, `contributing_factor_vehicle_1-5`, `vehicle_type_code_1-5`

**`stg_vehicles`** (grain: one row per vehicle per crash)
- `unique_id` (PK), `collision_id` (FK → crashes), `vehicle_type`, `vehicle_make`, `vehicle_year`, `driver_sex`, `driver_license_status`, `pre_crash` (action before crash), `point_of_impact`, `contributing_factor_1`/`2`

**`stg_person`** (grain: one row per person per crash)
- `unique_id` (PK), `collision_id` (FK → crashes), `vehicle_id` (FK → vehicles, nullable for pedestrians), `person_type` (Occupant/Pedestrian/Bicyclist), `person_injury` (Injured/Killed/Unspecified), `person_age`, `person_sex`, `ejection`, `emotional_status`, `bodily_injury`

### Intermediate Layer
- **`int_vehicles_per_crash`** — vehicle count + list of contributing factors aggregated per `collision_id`
- **`int_person_injury_summary`** — person counts broken out by type (pedestrian/cyclist/motorist) and severity per `collision_id`

### Marts — Star Schema (core)
- **`fct_crashes`** (grain: one row per crash) — `collision_id`, date/time, location, injury/fatality counts, FKs to dimensions
- **`dim_vehicles`** — vehicle type, make, year, contributing factors (deduplicated reference data)
- **`dim_persons`** — person type, demographics, injury severity

### Marts — BI Layer
- **`fct_crash_details`** — flattened join of `fct_crashes` + relevant vehicle/person aggregates, ready for Looker Studio direct consumption

---

## Status

### ✅ Decided
- [x] Domain: Car incidents (NYC collisions)
- [x] Data source: NYC Open Data (Socrata SODA API) — Crashes, Vehicles, Person tables
- [x] Cloud platform: AWS
- [x] Raw storage: S3
- [x] Warehouse/query layer: Athena
- [x] Transformation: dbt Cloud
- [x] Orchestration: Airflow via Docker (WSL2)
- [x] Dashboard: Looker Studio
- [x] Data quality strategy: dbt built-in tests (not_null, unique, relationships, accepted_values)

### 🔄 In Progress / Pending
- [x] Step 1: Schema/data model design (staging → intermediate → marts)
- [x] **Step 2: Git/GitHub repo setup** — GitHub account created, Git for Windows + GitHub CLI installed and authenticated (`gh auth login`), local repo initialized at `D:\Projects\nyc-collisions-data-engineering` with `dags/`, `dbt/`, `ingestion/`, `docs/` folder structure. Full walkthrough: [`docs/git-setup.md`](./docs/git-setup.md)
- [x] **Step 3: AWS setup** — Account, MFA, billing alerts, IAM user, S3 bucket (`nyc-collisions-gustavo-raw`), Athena query settings + `nyc_collisions` database. Full details: [`docs/aws-setup.md`](./docs/aws-setup.md)
- [x] **Step 4: Python ingestion script** (Socrata API → S3) — complete. All 3 tables fully ingested (Crashes: 2,269,187 / Vehicles: 4,551,002 / Person: 5,984,110 records). Full details: [`docs/ingestion-setup.md`](./docs/ingestion-setup.md)
- [x] **Step 5: Athena table definitions** — complete. Glue Crawler + manual review; found and fixed a major JSON-format bug (array vs. NDJSON); row-count sanity check passed exactly for all 3 tables. Full details: [`docs/athena-setup.md`](./docs/athena-setup.md)
- [ ] **Step 6: dbt Cloud setup** — in progress. Account, Athena connection, and GitHub repo connection all working (after resolving 3 gotchas — see [`docs/dbt-setup.md`](./docs/dbt-setup.md)); dbt project initialized. Next: build staging models. — **currently here**
- [ ] Step 7: Airflow (Docker) DAG — orchestrates ingestion + dbt Cloud trigger
- [ ] Step 8: Looker Studio dashboard (connect to marts, build visuals)
- [ ] Step 9: Documentation/polish (architecture diagram, resume write-up)

---

## Learning Goals Covered
Cloud storage · Web APIs · SQL · Python · Data warehousing · dbt (transformation + testing) · Airflow (orchestration) · Git/GitHub · Data quality · Data management · Dashboards/visualization

---

*This README is a living document and will be updated as project decisions and implementation progress.*
