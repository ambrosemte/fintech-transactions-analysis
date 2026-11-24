# Findings & Recommendations — Synthetic Fintech Transactions Analysis

*Personal portfolio project. All figures below come directly from running `run_all.py` on the deterministic synthetic dataset (`seed=42`, 50,048 transactions across 2,500 users, Jan–Dec 2025).*

---

## 1. GatewayBeta Drives Disproportionate Failure Volume and Experienced a Severe August Outage
- **Evidence:** Across the full year, `GatewayBeta` recorded a **6.93%** failure rate (₦17.96M in failed volume) compared with **3.77%** on `GatewayAlpha` and **5.14%** on `GatewayGamma`. On high-value transactions (≥ ₦20,000), `GatewayBeta` failed **6.63%** of attempts (₦13.48M failed volume). Daily failure ranking pinpoints a severe outage on **2025-08-14 (66.67% failure rate, 34/51 failed)** and **2025-08-15 (38.30%, 18/47 failed)**.
- **Recommendation:** Implement automated health-based circuit-breaking and failover routing: when a gateway's rolling 15-minute failure rate exceeds 15%, automatically shift new traffic—especially transfers ≥ ₦20,000—to `GatewayAlpha` until health checks recover.

## 2. Transfers Dominate GMV, While Data and Electricity Drive Fee Margin
- **Evidence:** Successful `transfers` account for **69.09% of GMV** (₦486.50M) but generate only **9.22% of fee revenue** (₦255,725) due to the flat ₦25 fee structure. Conversely, `data` generates **45.55% of total fee revenue** (₦1,263,346) on just **8.97% of GMV** (₦63.17M), and `electricity` adds another **19.55%** (₦542,200).
- **Recommendation:** Treat transfers as an acquisition/retention wedge while optimizing conversion and uptime for `data` and `electricity` bundles (e.g., saved beneficiaries, recurring bill reminders, and priority gateway routing for billers) to protect unit economics.

## 3. Duplicate-Charge Anomalies Exposed ₦529,250 Across 49 Pairs
- **Evidence:** Using a `LAG()` window query partitioned by `(user_id, service, amount_ngn)` within a 120-second window detected **49 duplicate successful charge pairs** totaling **₦529,250.00** in customer exposure, occurring an average of **31.0 seconds apart** (including single duplicate debits up to **₦85,000** on transfers).
- **Recommendation:** Enforce client-generated idempotency keys on every debit endpoint, pair them with a short-lived duplicate-purchase guard (e.g., 60–120s lock on identical user/service/amount), and run a scheduled reconciliation job using Query 08 to flag any anomalies automatically.

## 4. Month-End Weekends Surge 68% Above Mid-Month Weekdays, Peaking at 12:00–18:00
- **Evidence:** Daily volume rises from **117.1 tx/day** (₦1.65M GMV/day) on mid-month weekdays (`Mon–Thu, Days 1–24`) to **197.0 tx/day** (₦2.83M GMV/day) on month-end weekends (`Fri–Sun, Days 25–31`)—a **+68.2% lift**. Hourly traffic peaks at **17:00** (3,782 transactions, 7.56% of daily volume), with 12:00–18:00 accounting for nearly half of all daily activity.
- **Recommendation:** Schedule database maintenance, settlement batch runs, and provider migrations between **01:00 and 04:00** (under 0.6% of daily traffic per hour), and pre-warm worker queues and gateway liquidity ahead of the 25th of each month.

## 5. Cohort Retention Stabilizes Between 31% and 41% by Month 5
- **Evidence:** Across the Jan–Jul 2025 signup cohorts, Month-1 active retention sits at **85.8%–94.4%** (first full calendar month after signup), drops to **50.9%–57.9%** by Month 3, and settles at **30.8%–41.1%** by Month 5. In addition, 9 of the top 10 highest-spending users are `tier_3` KYC accounts (each spending ₦1.09M–₦1.73M).
- **Recommendation:** Target Month-2 to Month-3 drop-off with automated lifecycle nudges (bill-pay reminders and cashback incentives on data/electricity) and streamline KYC upgrades from `tier_1` to `tier_3` to lift higher-value transaction volume.
