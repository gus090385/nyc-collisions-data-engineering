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

The script supports two modes via a command-line flag — no code changes needed to switch between them:

```
python ingestion/ingest.py --test    # test mode: ~1,000 rows per table only
python ingestion/ingest.py           # full run: all records, fully paginated
```

How it works: `TEST_MODE = "--test" in sys.argv` checks whether `--test` was typed after the script name. When `True`, the script fetches a single small page (1,000 rows) per table and stops; when `False` (default), it paginates through the entire dataset in 50,000-row batches until exhausted.

**Test run result (2026-08-27):** Successfully authenticated and uploaded ~1,000-row sample files for all three tables to their respective S3 folders — confirmed visually in the S3 console.

**Full run:** Not yet executed. Expected to take significantly longer than the test run — the Crashes table alone has roughly 2.3 million rows — so it should be run when the terminal can be left uninterrupted for a while (likely 15–60+ minutes depending on connection speed and API responsiveness).

## Next Steps
- [ ] Run the full ingestion (`python ingestion/ingest.py`, no flag) to pull all records for Crashes, Vehicles, and Person into S3
- [ ] Confirm full files landed correctly in S3 (check file sizes/row counts)
- [ ] Move to Step 5: define Athena tables over this raw S3 data
