"""
NYC Motor Vehicle Collisions - Data Ingestion Script
------------------------------------------------------
Pulls data from three related Socrata (NYC Open Data) tables:
  - Crashes  (h9gi-nx95)
  - Vehicles (bm4k-52h4)
  - Person   (f55k-p6yu)

For each table:
  1. Paginate through the Socrata API to fetch all records (or only records
     changed since the last run, in --incremental mode)
  2. Save the raw records to a local file in NDJSON format (one JSON object
     per line — required for Athena's JSON SerDe; a single wrapping JSON
     array is NOT supported and will fail at query time)
  3. Upload that file to the corresponding S3 folder

Credentials (Socrata API Key ID/Secret, AWS keys) are loaded from a local .env
file (never committed to Git). Socrata authentication uses HTTP Basic Auth
(Key ID as username, Key Secret as password) — this is Socrata's current
API Key system, not the older X-App-Token header method.

INCREMENTAL MODE:
Socrata tracks a system field `:updated_at` on every row, set whenever a
record is created OR amended. In --incremental mode, this script queries
only rows changed since the last successful run, using a per-table
high-water-mark timestamp stored in S3 (s3://<bucket>/pipeline-state/last_run.json).
This state file lives in S3 (not locally) so it remains readable/writable
even if this script later runs inside ephemeral Airflow/Docker containers.

NOTE: because crash reports can be amended after the fact, an incremental
pull may re-fetch a collision_id/unique_id that already exists in an earlier
file, with updated values. This is expected — deduplication (keeping only the
most recently ingested version of each ID) happens downstream in dbt's
staging layer, not in this script.

Usage:
    python ingestion/ingest.py                          # full run, all 3 tables
    python ingestion/ingest.py --test                    # test mode: ~1000 records per table
    python ingestion/ingest.py --tables person            # full run, only the 'person' table
    python ingestion/ingest.py --tables crashes,person     # full run, only these tables
    python ingestion/ingest.py --incremental               # only records changed since last run
    python ingestion/ingest.py --incremental --tables person  # incremental, one table only
    python ingestion/ingest.py --seed-state                 # initialize state (no data fetched) —
                                                              # run this ONCE after an existing full
                                                              # pull, before ever using --incremental
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone

import requests
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# --- Configuration ---------------------------------------------------------

load_dotenv()  # reads variables from .env into environment

SOCRATA_KEY_ID = os.getenv("SOCRATA_KEY_ID")
SOCRATA_KEY_SECRET = os.getenv("SOCRATA_KEY_SECRET")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

SOCRATA_BASE_URL = "https://data.cityofnewyork.us/resource"

# Each source table: Socrata dataset ID -> S3 folder name
ALL_TABLES = {
    "crashes": "h9gi-nx95",
    "vehicles": "bm4k-52h4",
    "person": "f55k-p6yu",
}


def _resolve_tables_to_run() -> dict:
    """
    Determine which tables to process based on an optional --tables flag.
    --tables person            -> only 'person'
    --tables crashes,person    -> only 'crashes' and 'person'
    (no --tables flag)         -> all tables
    """
    if "--tables" in sys.argv:
        idx = sys.argv.index("--tables")
        try:
            requested = sys.argv[idx + 1]
        except IndexError:
            raise ValueError("--tables flag requires a value, e.g. --tables person")

        selected_names = [name.strip() for name in requested.split(",")]
        invalid = [name for name in selected_names if name not in ALL_TABLES]
        if invalid:
            raise ValueError(
                f"Unknown table name(s): {invalid}. Valid options: {list(ALL_TABLES.keys())}"
            )
        return {name: ALL_TABLES[name] for name in selected_names}

    return ALL_TABLES


TABLES = _resolve_tables_to_run()

PAGE_SIZE = 50000  # Socrata's max recommended page size per request
LOCAL_RAW_DIR = "ingestion/raw_data"  # temp local landing zone before upload

TEST_MODE = "--test" in sys.argv
TEST_ROW_LIMIT = 1000  # rows per table when running with --test

INCREMENTAL_MODE = "--incremental" in sys.argv
SEED_STATE_MODE = "--seed-state" in sys.argv
STATE_FILE_S3_KEY = "pipeline-state/last_run.json"  # tracks per-table high-water marks

# --- Logging -----------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# --- Functions ---------------------------------------------------------------

def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


def load_pipeline_state() -> dict:
    """
    Read the last-run state file from S3 (s3://<bucket>/pipeline-state/last_run.json).
    Returns an empty dict if the file doesn't exist yet (e.g. first-ever incremental run).
    Format: {"crashes": "2026-07-31T00:00:00.000", "vehicles": "...", "person": "..."}
    """
    s3_client = get_s3_client()
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=STATE_FILE_S3_KEY)
        state = json.loads(response["Body"].read())
        logger.info(f"Loaded pipeline state from S3: {state}")
        return state
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.info("No existing pipeline state file found in S3 — treating as first run.")
            return {}
        raise


def save_pipeline_state(state: dict) -> None:
    """
    Write the updated last-run state file back to S3.
    """
    s3_client = get_s3_client()
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=STATE_FILE_S3_KEY,
        Body=json.dumps(state, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info(f"Saved updated pipeline state to S3: {state}")


def fetch_table_data(dataset_id: str, table_name: str, since_timestamp: str | None = None) -> list[dict]:
    """
    Paginate through a Socrata dataset and return all records as a list of dicts.
    If `since_timestamp` is provided (incremental mode), only records with
    :updated_at greater than that timestamp are fetched.
    """
    all_records = []
    offset = 0
    auth = (SOCRATA_KEY_ID, SOCRATA_KEY_SECRET) if SOCRATA_KEY_ID and SOCRATA_KEY_SECRET else None

    page_size = TEST_ROW_LIMIT if TEST_MODE else PAGE_SIZE
    mode_label = " [TEST MODE]" if TEST_MODE else (" [INCREMENTAL]" if since_timestamp else "")

    logger.info(f"Starting fetch for '{table_name}' (dataset {dataset_id}){mode_label}")
    if since_timestamp:
        logger.info(f"  Filtering to records updated after: {since_timestamp}")

    while True:
        url = f"{SOCRATA_BASE_URL}/{dataset_id}.json"
        params = {
            "$limit": page_size,
            "$offset": offset,
            "$order": ":id",  # stable ordering across paginated requests
        }
        if since_timestamp:
            params["$where"] = f":updated_at > '{since_timestamp}'"

        response = requests.get(url, auth=auth, params=params, timeout=60)
        response.raise_for_status()

        page = response.json()
        if not page:
            break  # no more records

        all_records.extend(page)
        logger.info(f"  {table_name}: fetched {len(page)} records (total so far: {len(all_records)})")

        if TEST_MODE:
            break  # test mode only ever fetches one page (~1000 rows)

        offset += page_size

        if len(page) < page_size:
            break  # last page was partial, meaning we've reached the end

        time.sleep(0.5)  # small delay to be a polite API consumer

    logger.info(f"Finished '{table_name}': {len(all_records)} total records")
    return all_records


def save_local_json(records: list[dict], table_name: str, run_timestamp: str) -> str:
    """
    Save records to a local file in NDJSON (newline-delimited JSON) format —
    one complete JSON object per line, with NO wrapping array and NO commas
    between records. Returns the local file path.

    IMPORTANT: Athena's JSON readers (Hive JsonSerDe / OpenX JsonSerDe) require
    NDJSON and do NOT support a single file containing one large JSON array.
    Writing a plain array here (e.g. via json.dump(records, f)) will produce
    files that upload successfully but fail at Athena query time with
    'HIVE_CURSOR_ERROR: Row is not a valid JSON Object'.
    """
    os.makedirs(LOCAL_RAW_DIR, exist_ok=True)
    file_name = f"{table_name}_{run_timestamp}.json"
    file_path = os.path.join(LOCAL_RAW_DIR, file_name)

    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record))
            f.write("\n")

    logger.info(f"Saved local file (NDJSON): {file_path}")
    return file_path


def upload_to_s3(local_file_path: str, table_name: str, run_timestamp: str) -> None:
    """
    Upload a local file to the appropriate S3 folder for this table.
    """
    s3_client = get_s3_client()

    file_name = f"{table_name}_{run_timestamp}.json"
    s3_key = f"{table_name}/{file_name}"

    s3_client.upload_file(local_file_path, S3_BUCKET_NAME, s3_key)
    logger.info(f"Uploaded to s3://{S3_BUCKET_NAME}/{s3_key}")


def validate_config() -> None:
    """
    Basic sanity check that required environment variables are present
    before making any network calls.
    """
    missing = []
    if not AWS_ACCESS_KEY_ID:
        missing.append("AWS_ACCESS_KEY_ID")
    if not AWS_SECRET_ACCESS_KEY:
        missing.append("AWS_SECRET_ACCESS_KEY")
    if not S3_BUCKET_NAME:
        missing.append("S3_BUCKET_NAME")

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables in .env: {', '.join(missing)}"
        )

    if not SOCRATA_KEY_ID or not SOCRATA_KEY_SECRET:
        logger.warning(
            "SOCRATA_KEY_ID / SOCRATA_KEY_SECRET not set — proceeding without authentication. "
            "Socrata's SODA3 API now requires auth/identification for most requests, "
            "so unauthenticated calls may be rejected (403)."
        )


# --- Main ----------------------------------------------------------------

def main():
    validate_config()

    if SEED_STATE_MODE:
        # Mark the current moment as the high-water mark for all tables, WITHOUT
        # fetching or uploading any data. Use this once, right after a full pull
        # already completed by other means, so the next --incremental run only
        # picks up genuinely new/changed records instead of re-pulling everything.
        seed_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        seeded_state = {table_name: seed_timestamp for table_name in TABLES}
        save_pipeline_state(seeded_state)
        logger.info(f"Seeded pipeline state for tables {list(TABLES.keys())} at {seed_timestamp}")
        logger.info("No data was fetched. Future --incremental runs will start from this point.")
        return

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_datetime_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    mode_label = " (TEST MODE — limited rows)" if TEST_MODE else (" (INCREMENTAL)" if INCREMENTAL_MODE else "")
    logger.info(f"=== Starting ingestion run: {run_timestamp}{mode_label} ===")

    # Load prior state if running incrementally (ignored entirely otherwise)
    pipeline_state = load_pipeline_state() if INCREMENTAL_MODE else {}
    updated_state = dict(pipeline_state)  # copy to update as tables succeed

    for table_name, dataset_id in TABLES.items():
        try:
            since_timestamp = pipeline_state.get(table_name) if INCREMENTAL_MODE else None

            if INCREMENTAL_MODE and not since_timestamp:
                logger.info(
                    f"  No prior state for '{table_name}' — this will run as a full pull "
                    f"and establish the initial high-water mark."
                )

            records = fetch_table_data(dataset_id, table_name, since_timestamp=since_timestamp)

            if not records:
                logger.warning(f"No new/changed records for '{table_name}' — nothing to upload.")
                # Still advance the high-water mark to "now" so we don't re-check the same
                # empty window forever.
                if INCREMENTAL_MODE:
                    updated_state[table_name] = run_datetime_iso
                continue

            local_path = save_local_json(records, table_name, run_timestamp)
            upload_to_s3(local_path, table_name, run_timestamp)

            if INCREMENTAL_MODE:
                updated_state[table_name] = run_datetime_iso

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for '{table_name}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing '{table_name}': {e}")

    if INCREMENTAL_MODE:
        save_pipeline_state(updated_state)

    logger.info("=== Ingestion run complete ===")


if __name__ == "__main__":
    main()
