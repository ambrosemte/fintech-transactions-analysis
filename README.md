# Fintech Transactions Analysis (Python + SQLite + SQL)

*Personal portfolio project by Ambrose Makai. All users, payment gateways, and transaction records are **100% synthetic** and generated deterministically with `seed=42` (`scripts/generate_data.py`). No real company names, customer data, or credentials are used.*

## Problem
Digital wallet and bill-payment platforms process thousands of daily transactions across multiple payment gateways and services. Without structured SQL monitoring, operational teams miss silent revenue leaks: degraded payment gateways, multi-hour outages, duplicate-charge bugs from client retries, and month-end traffic surges.

This project builds a reproducible end-to-end analytics pipeline that generates a 12-month synthetic NGN transaction ledger (~50k rows), loads it into SQLite, executes 12 analytical SQL queries (CTEs and window functions), renders 5 charts, and distills concrete operational recommendations in [`findings.md`](findings.md).

## Project Structure
```text
fintech-transactions-analysis/
├── scripts/
│   ├── generate_data.py   # Deterministic synthetic data generator (seed=42) + SQLite loader
│   └── analyze.py         # Runs 12 SQL queries and renders 5 matplotlib charts
├── sql/
│   └── queries.sql        # 12 analytical SQL queries (CTEs, RANK, LAG, cohort retention)
├── tests/
│   └── test_pipeline.py   # Automated pytest verification of generation, SQL & charts
├── outputs/
│   ├── charts/            # 5 generated PNG charts
│   ├── query_results.json # Raw JSON output of all 12 SQL queries
│   └── summary.txt        # Formatted tabular output of all 12 SQL queries
├── run_all.py             # Single command to reproduce the entire pipeline
├── findings.md            # 5 concrete insights and recommendations from actual output
└── requirements.txt
```

## How to Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Reproduce dataset, SQLite DB, SQL query outputs, and all 5 charts
python run_all.py

# Run automated verification tests
pytest -v
```

## Results (Actual Output, `seed=42`)
- **Dataset:** 50,048 transactions across 2,500 synthetic users (Jan–Dec 2025).
- **Overall Success:** 46,272 successful transactions (**92.46%**), **₦704,131,150** GMV, **₦2,773,526.75** fee revenue; 2,562 failed (**5.12%**, ₦39.58M failed volume).
- **Gateway Failure Rates:** `GatewayBeta` **6.93%** vs. `GatewayGamma` **5.14%** vs. `GatewayAlpha` **3.77%**.
- **Outage Isolation:** `RANK()` over daily gateway failure rates isolated the simulated `GatewayBeta` outage on **2025-08-14 (66.67% failed)** and **2025-08-15 (38.30% failed)**.
- **Duplicate-Charge Detection:** `LAG()` window query flagged **49 duplicate pairs** within 120 seconds, representing **₦529,250.00** in exposure (mean **31.0s** apart).
- **Charts Generated:**
  - `outputs/charts/01_gateway_failure_rates.png`
  - `outputs/charts/02_revenue_by_service.png`
  - `outputs/charts/03_gateway_outage_august.png`
  - `outputs/charts/04_hourly_volume.png`
  - `outputs/charts/05_retention_cohorts.png`

See [`findings.md`](findings.md) for the full breakdown of all 5 insights and operational recommendations.

## Limitations
- The dataset is synthetic; real payment ledgers include partial settlements, multi-leg fee splits, chargebacks, and timezone/clock-skew edge cases not modeled here.
- Duplicate-charge detection uses a heuristic `(user_id, service, amount_ngn, <=120s)` window; legitimate repeat airtime purchases for different phone numbers could trigger false positives without a `recipient_ref` column.
- SQLite is ideal for single-file reproducibility, whereas production analytics would run on PostgreSQL or a columnar warehouse (e.g., DuckDB/BigQuery).

## What I Would Do Next
- Add a `recipient_account` / `idempotency_key` column to separate true double-debits from legitimate repeat purchases.
- Add automated anomaly-detection alerts (z-score / rolling failure-rate threshold) that output a daily incident digest.
- Package the SQL queries as dbt models with schema and freshness tests.
