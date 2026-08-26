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
- [ ] **Step 4: Python ingestion script** (Socrata API → S3) — **currently here**
- [ ] Step 5: Athena table definitions (raw S3 data → queryable tables)
- [ ] Step 6: dbt Cloud setup (connect to Athena, build staging/intermediate/marts models + tests)
- [ ] Step 7: Airflow (Docker) DAG — orchestrates ingestion + dbt Cloud trigger
- [ ] Step 8: Looker Studio dashboard (connect to marts, build visuals)
- [ ] Step 9: Documentation/polish (architecture diagram, resume write-up)

---

## Learning Goals Covered
Cloud storage · Web APIs · SQL · Python · Data warehousing · dbt (transformation + testing) · Airflow (orchestration) · Git/GitHub · Data quality · Data management · Dashboards/visualization

---

*This README is a living document and will be updated as project decisions and implementation progress.*
