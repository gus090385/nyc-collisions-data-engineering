# AWS Setup

This document records how AWS was configured for this project, step by step.

## 1. AWS Account Created
- Signed up at aws.amazon.com, selected the **"Paid"** account plan (not the 6-month "Free" plan) — the "Free" plan auto-closes the account after 6 months or when $200 in credits is used, which is unsuitable for a portfolio project meant to stay live long-term. The "Paid" plan simply switches to standard pay-as-you-go pricing after credits are used, with no auto-close.
- Selected **Basic support - Free** plan (sufficient for a personal project).
- Did **not** enable the Canada West (Calgary) region during signup — standardized on **US East (N. Virginia) / us-east-1** instead, since it has the most complete free-tier service availability and is the most commonly documented region.

## 2. Root Account Security
- Enabled **MFA (multi-factor authentication)** on the root account via an authenticator app (Console → account name → Security credentials → Assign MFA device → scan QR code → confirm two consecutive codes).
- Root account is now reserved for account-level tasks only (billing, account settings) — not used for day-to-day work.

## 3. Billing Safety Net
- Enabled **"Receive Free Tier Usage Alerts"** in Billing Preferences (emails when approaching free-tier limits).
- Created a budget alert (Billing → Budgets) to get notified of any unexpected spend.

## 4. IAM User (used for all daily work instead of root)
- Created an IAM user: **`data-eng-user`**
- Enabled AWS Management Console access with a custom password.
- Attached policy: **AdministratorAccess** (simplest option for a solo learning project; a real production setup would scope this down to least-privilege, e.g. S3 + Athena + Glue only).
- Logged in going forward via the IAM sign-in URL using `data-eng-user`, not the root account.

## 5. S3 Bucket (raw data storage)
- **Bucket name:** `nyc-collisions-gustavo-raw`
- **Region:** US East (N. Virginia) — `us-east-1`
- **Bucket type:** General purpose
- **Object Ownership:** ACLs disabled (recommended) / Bucket owner enforced — access controlled purely via IAM policies, not legacy ACLs.
- **Block Public Access:** Enabled (kept default — raw data should never be public)
- **Versioning:** Off (kept simple for this project)
- **Encryption:** Default (SSE-S3)

### Folder structure inside the bucket
```
nyc-collisions-gustavo-raw/
├── crashes/
├── vehicles/
├── person/
└── athena-query-results/
```
Each of `crashes/`, `vehicles/`, `person/` will hold raw JSON/CSV extracts from the corresponding Socrata API table, landed there by the Python ingestion script (Step 4). `athena-query-results/` stores Athena's query output files, kept separate from raw data.

## 6. Athena Setup
- Opened Athena in the **classic Query editor** (not "SageMaker Unified Studio," which AWS now nudges new users toward — the classic editor is simpler and sufficient for this project).
- Configured **query result location**: `s3://nyc-collisions-gustavo-raw/athena-query-results/` (Query settings tab → Manage → Query result encryption).
- Left encryption and bucket-owner-control options off/default — not needed for a personal project.
- Created a dedicated database via SQL in the query editor:
  ```sql
  CREATE DATABASE nyc_collisions;
  ```
- Selected `nyc_collisions` as the active database (instead of the default `default` database) — this is where all Athena tables for this project (crashes, vehicles, person, and later dbt models) will live.

## Next Steps (to be added to this doc as completed)
- [ ] (Optional) Scope IAM permissions down from AdministratorAccess to least-privilege for S3/Athena/Glue only
- [ ] Note S3 bucket ARN / URI for use in Python ingestion script and Athena table DDL
