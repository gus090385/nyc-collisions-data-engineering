# Athena Table Definitions (Step 5)

This document covers how raw S3 data was exposed as queryable Athena tables.

## Approach: Hybrid (Glue Crawler + Manual Review)

Rather than hand-writing `CREATE EXTERNAL TABLE` DDL for three wide tables (Crashes, Vehicles, Person — each with 25–45+ columns), a hybrid approach was used:
1. **AWS Glue Crawler** does the initial heavy lifting — scanning S3, inferring schema, and registering tables automatically.
2. **Manual review** in the Glue/Athena console afterward to sanity-check the inferred schema (column names, types).

This mirrors common real-world practice — most data engineers don't hand-write DDL for wide semi-structured source data; they crawl first, then refine. AWS Glue itself is also a frequently requested skill in data engineering job postings.

## 1. Custom Classifier (later found unnecessary — see Section 3)

Initially created a custom Glue classifier to handle what was believed to be JSON-array-formatted source files:
- **Name:** `json-array-classifier`
- **Type:** JSON
- **JSON path:** `$[*]` (tells Glue: "the file is a JSON array; treat each element as one row")

This was attached to the crawler. It turned out to be unnecessary once the underlying data format issue (Section 3) was fixed — Glue's default built-in JSON classifier handles NDJSON natively. The custom classifier remains attached but is simply skipped in favor of the default when it doesn't match.

## 2. IAM Role for Glue

Created a dedicated IAM role for the crawler to assume:
- **Name:** `AWSGlueServiceRole-nyc-collisions`
- **Trusted entity:** AWS service → Glue
- **Attached policies:** `AWSGlueServiceRole` (managed policy — baseline Glue permissions) + `AmazonS3ReadOnlyAccess` (read access to the bucket)

## 3. Crawler Setup

- **Name:** `nyc-collisions-crawler`
- **Data sources:** three separate S3 paths, each becoming its own table:
  - `s3://nyc-collisions-gustavo-raw/crashes/`
  - `s3://nyc-collisions-gustavo-raw/vehicles/`
  - `s3://nyc-collisions-gustavo-raw/person/`
- **IAM role:** `AWSGlueServiceRole-nyc-collisions`
- **Target database:** `nyc_collisions` (the same database already created earlier directly in Athena — Athena and Glue share the same underlying Data Catalog)
- **Table prefix:** `raw_` → resulting tables: `raw_crashes`, `raw_vehicles`, `raw_person`
- **Schedule:** On demand (run manually for now; could be automated via Airflow later)

## 4. Bug: JSON Array Format Not Supported by Athena at Query Time

**Symptom:** After the crawler successfully created all three tables (schema looked correct), running a simple `SELECT COUNT(*) FROM raw_crashes` in Athena failed:
```
HIVE_CURSOR_ERROR: Failed to read file at s3://nyc-collisions-gustavo-raw/crashes/crashes_....json
```

**Root cause:** Athena's JSON SerDes (`Hive JsonSerDe`, `OpenX JsonSerDe`) require **NDJSON** (newline-delimited JSON — one JSON object per line) and cannot read a file containing a single large JSON array, which is what the ingestion script (Step 4) was producing via `json.dump(records, f)`. Schema **inference** (via the custom `$[*]` classifier) and query-time **reading** are handled by different code paths in Glue/Athena — the crawler succeeding did not mean queries would work.

**Fix (implemented in `ingestion/ingest.py`, documented fully in [`docs/ingestion-setup.md`](./ingestion-setup.md) Section 9):**
- Changed the script to write one JSON object per line (NDJSON), no wrapping array.
- Deleted the three malformed files from S3 and re-ran the full ingestion to regenerate them correctly.
- Re-ran the Glue Crawler against the corrected files (no reconfiguration needed).

## 5. Validation: Row-Count Sanity Check

With corrected NDJSON files in place, ran a basic count query against each table and compared to the record counts captured directly from the ingestion script's own logs:

```sql
SELECT COUNT(*) AS row_count FROM raw_crashes;
SELECT COUNT(*) AS row_count FROM raw_vehicles;
SELECT COUNT(*) AS row_count FROM raw_person;
```

| Table | Expected (from ingestion logs) | Athena Result | Match |
|---|---|---|---|
| Crashes | 2,269,187 | 2,269,187 | ✅ |
| Vehicles | 4,551,002 | 4,551,002 | ✅ |
| Person | 5,984,110 | 5,984,110 | ✅ |

**All three match exactly** — confirming the full pipeline (Socrata API → Python → S3 → Glue Crawler → Athena) works correctly end-to-end with no data loss or duplication.

## Next Steps
- [ ] Manually review inferred column names/types in the Glue console for each table; rename/adjust anything awkward (e.g., generic auto-detected names, incorrect type guesses)
- [ ] Move to Step 6: dbt Cloud setup (staging → intermediate → marts models on top of these raw tables)
