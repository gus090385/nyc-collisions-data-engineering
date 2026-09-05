# dbt Cloud Setup (Step 6)

This document covers how dbt Cloud was set up and connected to Athena for this project.

## 1. Account Creation

- Signed up for free at getdbt.com (Developer plan — free forever for solo use, no credit card required).
- Onboarding question ("How familiar are you with dbt?") answered as **"I am new to dbt"** — accurate for this first hands-on project.
- Project named: `nyc_collisions`

## 2. Athena Connection Settings

Configured under Settings → Connections → Athena:

| Field | Value |
|---|---|
| AWS region name | `us-east-1` |
| Database (catalog) | `nyc_collisions` |
| AWS S3 staging directory | `s3://nyc-collisions-gustavo-raw/athena-query-results/` (reuses the same folder configured for Athena itself in Step 3) |
| Athena workgroup | left blank → defaults to `primary` |

All "Optional settings" (Spark workgroup, S3 data directory, naming conventions, retry counts, etc.) were left at their defaults — not needed for this project's scale.

## 3. Personal Development Credentials

Under **Your profile → Credentials → nyc_collisions**:
- **AWS Access Key ID / Secret Access Key:** reused the existing `data-eng-user` IAM credentials (same ones from the CSV downloaded in Step 4).
- **Schema:** `dbt_gravell` — dbt Cloud's standard per-developer naming convention (`dbt_<username>`), keeping personal dev models separate from production.
- **Threads:** `4` (allows a few models to build in parallel).

## 4. Gotcha #1: dbt Cloud's "Fusion" Engine Doesn't Support Athena

**Symptom:** Running "Test connection" failed immediately with:
```
[error] [InvalidConfig (dbt1005)]: Failed to parse profiles.yml: unknown variant `athena`,
expected one of `redshift`, `snowflake`, `postgres`, `bigquery`, `trino`, `datafusion`,
`spark`, `databricks`, `salesforce`, `duckdb`, `alt`, `exasol`, `fabric`, `clickhouse`
```

**Root cause:** dbt Labs' newer **"Fusion"** engine (a Rust-based rewrite of dbt Core, currently in preview and apparently the new default for freshly created dbt Cloud environments) does not yet support Athena as an adapter — confirmed as an open, unresolved item on dbt Labs' public roadmap/issue tracker at the time of this project.

**Fix:** Every dbt Cloud **environment** (Development or Deployment) has its own "dbt version" setting, independent of the connection itself. This needed to be explicitly set to **"Compatible"** (the classic dbt Core release track) rather than "Fusion Stable." The Development environment's version now shows: *"dbt Compatible (Aligned to dbt Core)."*

**A useful confirmation, found later:** the dbt Cloud dashboard itself flags a "Fusion eligibility check failed" notice for this project, specifically citing *"Supported data platform: ✗ At least one environment is running on a supported data platform"* — independently confirming Athena isn't Fusion-compatible yet.

## 5. Gotcha #2: Development Environment Wasn't Actually Created

**Symptom:** After the Fusion issue above, navigating to "Environments" showed no Development environment at all, and the Credentials page displayed: *"This project does not have a development environment associated with it."*

**Root cause:** The initial onboarding wizard's "Configure your development environment" step had appeared to complete (green checkmark shown), but because the connection test failed at that point (Gotcha #1), the environment was never actually persisted.

**Fix:** Manually created a Development environment via Orchestration → Environments → Create new environment:
- **Environment type:** Development *(this dropdown defaults to "Deployment," which surfaces a different form entirely — needed to be explicitly switched)*
- **Name:** `Development`
- **dbt version:** `Compatible`
- **Connection:** `Athena`

After this, re-entering AWS credentials on the Credentials page and clicking "Test connection" succeeded: *"Your test completed successfully, you're good to go!"*

## 6. Gotcha #3: GitHub Repository Connection Needed Explicit App Installation

**Symptom:** Opening Studio (the dbt Cloud IDE) showed: *"Repository Setup Required — This project does not have a repository configured."*

**Root cause:** Similar to Gotcha #2 — the repository connection step during onboarding hadn't fully completed.

**Fix:**
1. Triggered the GitHub App installation flow ("Install dbt Cloud" on GitHub's side).
2. Chose **"Only select repositories"** (rather than "All repositories") and selected specifically `nyc-collisions-data-engineering` — scoping dbt Cloud's GitHub access to just this one repo, following least-privilege practice.
3. Verified the link directly in Project Settings, which then showed:
   - **Repository:** `git://github.com/gus090385/nyc-collisions-data-engineering.git` ✅
   - **Development connection:** `Athena` ✅
4. Studio then loaded correctly, showing the real repo contents (`docs/`, `ingestion/`, `.gitignore`, `README.md`) in its File Explorer.

## 7. dbt Project Initialization

Clicked **"Initialize dbt project"** in Studio, which scaffolded the standard dbt project structure directly into the connected repo:
```
nyc-collisions-data-engineering/
├── analyses/        (.gitkeep)
├── macros/          (.gitkeep)
├── models/
│   └── example/
│       ├── my_first_dbt_model.sql
│       ├── my_second_dbt_model.sql
│       └── schema.yml
├── seeds/           (.gitkeep)
├── snapshots/       (.gitkeep)
├── tests/           (.gitkeep)
└── dbt_project.yml
```

**Important workflow note:** `master` is a protected/locked branch in dbt Cloud's Studio (shown with a lock icon) — direct commits aren't permitted. Changes must be committed to a **new branch** first (`chore/initialize-dbt-project`), then merged into `master` via a Pull Request on GitHub. This mirrors standard real-world Git workflow (feature branches + PR review) and is a good practice to carry through the rest of this project's dbt work.

**Note on sync:** dbt Cloud's Studio commits directly to GitHub through its own integrated git client — not through the local terminal/VS Code workflow used in Steps 1–5. After merging any dbt Cloud commits into `master` on GitHub, remember to run `git pull` in the local project folder (`D:\Projects\nyc-collisions-data-engineering`) to keep the local clone in sync.

## Next Steps
- [ ] Merge the `chore/initialize-dbt-project` branch into `master` via a GitHub Pull Request
- [ ] `git pull` locally to sync the new dbt project files
- [ ] Delete the example models (`my_first_dbt_model.sql`, `my_second_dbt_model.sql`) — placeholders, not part of this project
- [ ] Configure `dbt_project.yml` (project name, model paths, materialization defaults)
- [ ] Build staging models (`stg_crashes`, `stg_vehicles`, `stg_person`) over the raw Athena tables (`raw_crashes`, `raw_vehicles`, `raw_person`)
- [ ] Add dbt generic tests (not_null, unique, relationships, accepted_values) per the project's data quality plan
