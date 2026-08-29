# Python Ingestion Script Setup

This document covers how the Python ingestion pipeline (Socrata API → S3) was built, configured, and tested.

## 1. Install Python & VS Code

- Checked for an existing Python install first (`python --version`) — Windows returned a Microsoft Store placeholder message rather than a real installation, confirming Python wasn't actually installed.
- Installed Python from **python.org** (the standalone installer, not the newer "Python install manager") — during setup, checked **"Add python.exe to PATH"** on the first screen (critical, easy to miss).
- Verified: `python --version` → `Python 3.14.7`, `pip --version` → confirmed working.
- VS Code was already installed; added the official Microsoft **Python extension** for syntax highlighting/IntelliSense.

## 2. Virtual Environment & Dependencies

From the project root (`D:\Projects\nyc-collisions-data-engineering`):
```
python -m venv venv
venv\Scripts\activate
pip install requests boto3 python-dotenv
pip freeze > ingestion/requirements.txt
```

- **`venv`**: an isolated Python environment scoped to this project, so its packages don't mix with other Python projects on the machine. Must be re-activated (`venv\Scripts\activate`) every time a new terminal is opened.
- **`requests`**: calls the Socrata API.
- **`boto3`**: AWS SDK for Python, used to upload files to S3.
- **`python-dotenv`**: loads credentials from a local `.env` file into environment variables at runtime.
- **`requirements.txt`**: records exact installed package versions so the environment can be reproduced elsewhere (`pip install -r requirements.txt`).

## 3. Credentials

### Socrata API Key
- Created via the NYC Open Data dataset page (Sign In → Developer Settings → Create New App Token/API Key) rather than a direct token-management URL (Socrata's UI has moved this around).
- Socrata generated an **API Key ID** and **API Key Secret** — this is Socrata's current ("SODA3") authentication system, which **replaced** the older simple app-token string.
- Both values were copied immediately (the secret is only shown once).

### AWS Access Key
- Created under IAM → `data-eng-user` → Security credentials → Create access key.
- Use case selected: **"Local code"** (running application code in a local development environment) — the more precise fit compared to "Application running outside AWS" (meant for on-prem/other datacenter infrastructure).
- Downloaded as a `.csv` file (safer than manually copying the secret) and moved outside the Git project folder.

### `.env` file
Created at the project root (`D:\Projects\nyc-collisions-data-engineering\.env`), excluded from Git via `.gitignore`:
```
SOCRATA_KEY_ID=your_api_key_id_here
SOCRATA_KEY_SECRET=your_api_key_secret_here
AWS_ACCESS_KEY_ID=your_aws_access_key_id_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=nyc-collisions-gustavo-raw
```
Verified `.env` is correctly ignored by Git via `git status` (should not appear as tracked or untracked).

## 4. The Ingestion Script (`ingestion/ingest.py`)

### What it does
For each of the three Socrata tables — Crashes (`h9gi-nx95`), Vehicles (`bm4k-52h4`), Person (`f55k-p6yu`) — the script:
1. **Paginates** through the Socrata API in batches (50,000 rows/page in full mode) until all records are retrieved.
2. **Saves locally** as a timestamped JSON file under `ingestion/raw_data/` (e.g. `crashes_20260828T034543Z.json`).
3. **Uploads to S3** into the matching folder (`crashes/`, `vehicles/`, `person/`) in bucket `nyc-collisions-gustavo-raw`.

### Why land data locally before uploading to S3, instead of streaming directly?
- **Resilience**: if the S3 upload fails partway (network blip, AWS hiccup), the data is still safely on disk and can be re-uploaded without re-calling the Socrata API (avoiding extra load on their rate limits).
- **Debuggability**: raw files can be inspected locally before they go anywhere.
- **Realism**: "land raw data locally/in a staging area, then push to cloud storage" is a standard, common real-world ingestion pattern — a fine thing to describe in an interview.

### Why does this run on a local machine rather than "in the cloud"?
There's no separate AWS compute service running this code (no Lambda, no EC2) — it's a script that has to be executed somewhere. Running it locally is free and simple for a portfolio project; paying for cloud compute to run an occasional script isn't necessary. Later, **Airflow** (running in Docker, still on this same laptop) will execute this script on a schedule automatically — that's the "orchestration" layer, not a change in where the code physically runs.

## 5. Authentication Bug Encountered & Fixed

**Symptom:** First test run returned `403 Client Error: Forbidden` on all three tables.

**Cause:** The script was originally written to send the Socrata credential via the `X-App-Token` HTTP header — this is the method for Socrata's **older**, simpler "Application Token" system. However, the credential actually created (API Key ID + API Key Secret) belongs to Socrata's **newer API Key system**, which must be sent via **HTTP Basic Authentication** (Key ID as username, Key Secret as password) — not the `X-App-Token` header.

**Fix:** Updated the script to authenticate using `requests`' built-in Basic Auth support:
```python
auth = (SOCRATA_KEY_ID, SOCRATA_KEY_SECRET)
response = requests.get(url, auth=auth, params=params, timeout=60)
```
Updated `.env` to store `SOCRATA_KEY_ID` and `SOCRATA_KEY_SECRET` separately (instead of a single `SOCRATA_APP_TOKEN` value).

**Context:** Socrata's newer SODA3 API now requires authentication/identification for most requests (a change aimed at reducing bot/scraper load), which is why the unauthenticated/mismatched-auth request was rejected outright rather than just rate-limited.

## 6. Test Mode vs. Full Run

The script supports two independent flags via command-line arguments — no code changes needed to switch behavior:

```
python ingestion/ingest.py --test              # test mode: ~1,000 rows per table only
python ingestion/ingest.py                     # full run: all records, all 3 tables
python ingestion/ingest.py --tables person      # full run, but only the named table(s)
python ingestion/ingest.py --tables crashes,person   # full run, multiple named tables
```

How it works:
- `TEST_MODE = "--test" in sys.argv` checks whether `--test` was typed after the script name. When `True`, the script fetches a single small page (1,000 rows) per table and stops.
- `--tables <name(s)>` filters which tables get processed at all, via a comma-separated list. Useful for re-running just one table after a partial/interrupted run, without re-fetching and re-uploading tables that already completed successfully.

**Test run result (2026-08-27):** Successfully authenticated and uploaded ~1,000-row sample files for all three tables to their respective S3 folders — confirmed visually in the S3 console.

**Full run:** Not yet executed. Expected to take significantly longer than the test run — the Crashes table alone has roughly 2.3 million rows — so it should be run when the terminal can be left uninterrupted for a while (likely 15–60+ minutes depending on connection speed and API responsiveness).

## 7. Recovering from an Interrupted Run

The first full-run attempt was interrupted by an unplanned computer restart partway through. Rather than blindly re-running the whole script (which would have created duplicate files for tables that had already finished — wasting storage and causing double-counted rows later), the situation was diagnosed as follows:

**How we determined what actually completed (inference, not a log file):**
- `run_timestamp` is generated once per script execution and reused across all three tables' filenames in that run — so matching timestamps across files (e.g., `crashes_20260828T042616Z.json` and `vehicles_20260828T042616Z.json` sharing `T042616Z`) confirm they came from the same run.
- The script only calls `upload_to_s3()` *after* a table's full fetch-and-local-save completes — so a real (non-empty) file appearing in S3 implies that table's full pipeline ran to completion. S3 doesn't list partial/failed uploads as objects.
- `person/` had no file matching that run's timestamp — only the earlier test file — indicating the run was interrupted before Person finished (or started) uploading.

**Conclusion:** Crashes (1.7 GB) and Vehicles (2.2 GB) completed successfully; Person did not.

**Fix attempted:** Added a `--tables` flag to the script (see Usage above) to re-run only the incomplete table:
```
python ingestion/ingest.py --tables person
```

### ⚠️ Second issue: running the script without the `python` prefix
The command was run as `ingest.py --tables person` (missing the `python` prefix). On Windows, invoking a `.py` file directly like this relies on a file-association handler, which does not reliably pass command-line arguments through to `sys.argv` — as a result, the `--tables person` filter was silently dropped, and the script fell back to its default behavior of processing **all three tables**, re-fetching and re-uploading Crashes and Vehicles unnecessarily (duplicate large files in S3) alongside the now-completed Person table.

**Lesson learned:** Always invoke Python scripts with the explicit `python` command:
```
python ingestion\ingest.py --tables person
```
Never run `ingest.py --tables person` directly on Windows.

### Cleanup performed
This accidental full re-run did, however, produce a **complete, consistent full run of all three tables** in a single execution (run timestamp `T054618Z`), with real record counts captured in the logs:

| Table | Total Records |
|---|---|
| Crashes | 2,269,187 |
| Vehicles | 4,551,002 |
| Person | 5,984,110 |

Since Crashes and Vehicles now had two full files each (the earlier `T042616Z` versions and the new `T054618Z` versions), the **older duplicate files were deleted** from S3, keeping one clean, consistent set of full files (all three sharing timestamp `T054618Z`) plus the original small test files in each folder.

**Final state per folder:** 1 small test file (~300–750 KB) + 1 full data file — no duplicates.

### ⚠️ Verification caveat
The row counts above come directly from the ingestion script's own logs (confirmed, not inferred this time). **Planned sanity check once Athena is set up (Step 5):** query row counts for `crashes`, `vehicles`, and `person` tables in Athena and confirm they match these numbers (2,269,187 / 4,551,002 / 5,984,110) — validates that S3 → Athena table definitions aren't dropping or duplicating rows.

## 8. Incremental Ingestion Design

A natural question for any pipeline: how do we detect and pull only *new* data from the source on subsequent runs, instead of re-pulling everything every time?

### Mechanism: Socrata's `:updated_at` system field
Socrata automatically tracks a system field `:updated_at` on every row, set whenever a record is created **or amended**. Records can be filtered using SoQL's `$where` parameter:
```
$where=:updated_at > '2026-08-29T02:27:42.739'
```
**Gotcha:** system fields must be referenced with a **leading colon** in SoQL (`:updated_at`, not `updated_at`) in both `$where` and `$select` clauses. Omitting the colon returns a `400 Bad Request`.

### State tracking: stored in S3, not locally
The script tracks a per-table "high-water mark" (the timestamp of the last successful run) in a small state file: `s3://nyc-collisions-gustavo-raw/pipeline-state/last_run.json`. This lives in **S3 rather than on the local machine** so it remains readable/writable even after this script is later run inside ephemeral Airflow/Docker containers (Step 7), which may not persist local disk state between runs.

Example state file contents:
```json
{
  "crashes": "2026-08-29T02:34:24.451",
  "vehicles": "2026-08-29T02:34:24.451",
  "person": "2026-08-29T02:34:24.451"
}
```

### New script flags
```
python ingestion/ingest.py --seed-state       # initialize state file with "now", no data fetched
python ingestion/ingest.py --incremental       # fetch only records changed since last state
```

**`--seed-state`** was necessary because a full pull had already been completed manually before incremental mode existed — running `--incremental` without seeding first would have had no prior state to compare against, causing it to treat the run as "first ever" and re-pull everything, undoing the clean, deduplicated S3 state. Running `--seed-state` once establishes a baseline ("everything before this moment is already captured") without touching S3 data.

### Handling amended records (expected duplicates across files)
Because crash reports can be revised after the fact (per NYC's own dataset notes: *"the data is preliminary and subject to change when the MV-104AN forms are amended"*), an incremental pull may legitimately re-fetch a `collision_id`/`unique_id` that already exists in an earlier file, just with updated field values. **This is expected, not a bug.** Deduplication — keeping only the most recently ingested version of each ID — is handled downstream in dbt's staging layer (Step 6), typically via `ROW_NUMBER() OVER (PARTITION BY id ORDER BY ingested_at DESC)`, keeping only row #1 per ID. The ingestion script's job is simply to land all versions; deduplication is a modeling decision, not an ingestion one.

### Known source-side limitation (as of this writing)
NYC Open Data's Crashes and Vehicles datasets are currently flagged as **temporarily not updating** while their automated update process is being fixed (expected resolution: August 2026; last actual data update: July 31, 2026). This was verified directly against the dataset's public status note. Practical implication: incremental runs during this window will correctly return 0 new/changed records — this was confirmed in testing and is the *expected*, correct behavior, not a sign of a broken pipeline.

### Testing performed
1. Ran `--seed-state` once → state file created in S3 with current timestamp for all 3 tables.
2. Ran `--incremental` → initially failed with `400 Bad Request` due to the missing colon on `:updated_at` (see Gotcha above); fixed and re-ran.
3. Re-ran `--incremental` → succeeded, correctly returned 0 records for all 3 tables (consistent with the known source-side update pause), and advanced the state file's timestamps.

## Next Steps
- [x] Run the full ingestion for all three tables (completed via the accidental-but-successful full re-run, `T054618Z`)
- [x] Confirm full files landed correctly in S3 (verified: 1 test + 1 full file per folder, duplicates cleaned up)
- [x] Design and implement incremental ingestion (`--incremental` / `--seed-state`), tested successfully
- [ ] **Sanity check:** once Athena tables are defined, compare row counts per table against the confirmed totals above (2,269,187 / 4,551,002 / 5,984,110)
- [ ] Move to Step 5: define Athena tables over this raw S3 data
- [ ] (Future, Step 7) Wire `--incremental` into the Airflow DAG for scheduled runs
