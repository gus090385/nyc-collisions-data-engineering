"""
NYC Motor Vehicle Collisions - Data Ingestion Script
------------------------------------------------------
Pulls data from three related Socrata (NYC Open Data) tables:
  - Crashes  (h9gi-nx95)
  - Vehicles (bm4k-52h4)
  - Person   (f55k-p6yu)

For each table:
  1. Paginate through the Socrata API to fetch all records
  2. Save the raw JSON response to a local file
  3. Upload that file to the corresponding S3 folder

Credentials (Socrata API Key ID/Secret, AWS keys) are loaded from a local .env
file (never committed to Git). Socrata authentication uses HTTP Basic Auth
(Key ID as username, Key Secret as password) — this is Socrata's current
API Key system, not the older X-App-Token header method.

Usage:
    python ingestion/ingest.py            # full run (all records)
    python ingestion/ingest.py --test      # test mode: ~1000 records per table only
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone

import requests
import boto3
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
TABLES = {
    "crashes": "h9gi-nx95",
    "vehicles": "bm4k-52h4",
    "person": "f55k-p6yu",
}

PAGE_SIZE = 50000  # Socrata's max recommended page size per request
LOCAL_RAW_DIR = "ingestion/raw_data"  # temp local landing zone before upload

TEST_MODE = "--test" in sys.argv
TEST_ROW_LIMIT = 1000  # rows per table when running with --test

# --- Logging -----------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# --- Functions ---------------------------------------------------------------

def fetch_table_data(dataset_id: str, table_name: str) -> list[dict]:
    """
    Paginate through a Socrata dataset and return all records as a list of dicts.
    """
    all_records = []
    offset = 0
    auth = (SOCRATA_KEY_ID, SOCRATA_KEY_SECRET) if SOCRATA_KEY_ID and SOCRATA_KEY_SECRET else None

    page_size = TEST_ROW_LIMIT if TEST_MODE else PAGE_SIZE
    mode_label = " [TEST MODE]" if TEST_MODE else ""

    logger.info(f"Starting fetch for '{table_name}' (dataset {dataset_id}){mode_label}")

    while True:
        url = f"{SOCRATA_BASE_URL}/{dataset_id}.json"
        params = {
            "$limit": page_size,
            "$offset": offset,
            "$order": ":id",  # stable ordering across paginated requests
        }

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
    Save records to a local JSON file. Returns the local file path.
    """
    os.makedirs(LOCAL_RAW_DIR, exist_ok=True)
    file_name = f"{table_name}_{run_timestamp}.json"
    file_path = os.path.join(LOCAL_RAW_DIR, file_name)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(records, f)

    logger.info(f"Saved local file: {file_path}")
    return file_path


def upload_to_s3(local_file_path: str, table_name: str, run_timestamp: str) -> None:
    """
    Upload a local file to the appropriate S3 folder for this table.
    """
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )

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

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode_label = " (TEST MODE — limited rows)" if TEST_MODE else ""
    logger.info(f"=== Starting ingestion run: {run_timestamp}{mode_label} ===")

    for table_name, dataset_id in TABLES.items():
        try:
            records = fetch_table_data(dataset_id, table_name)

            if not records:
                logger.warning(f"No records fetched for '{table_name}' — skipping upload.")
                continue

            local_path = save_local_json(records, table_name, run_timestamp)
            upload_to_s3(local_path, table_name, run_timestamp)

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for '{table_name}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing '{table_name}': {e}")

    logger.info("=== Ingestion run complete ===")


if __name__ == "__main__":
    main()
