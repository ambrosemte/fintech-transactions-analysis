-- Analytical SQL queries for synthetic NGN wallet & bill-payment transactions.
-- Each query is delimited by `-- name: <query_name>`.

-- name: 01_status_overview
SELECT
    status,
    COUNT(*) AS tx_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
    ROUND(SUM(amount_ngn), 2) AS total_amount_ngn,
    ROUND(SUM(fee_ngn), 2) AS total_fee_ngn
FROM transactions
GROUP BY status
ORDER BY tx_count DESC;

-- name: 02_failure_rate_by_gateway
WITH gateway_stats AS (
    SELECT
        gateway,
        COUNT(*) AS total_tx,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_tx,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_tx,
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_tx,
        SUM(CASE WHEN status = 'reversed' THEN 1 ELSE 0 END) AS reversed_tx,
        ROUND(AVG(amount_ngn), 2) AS avg_amount_ngn,
        ROUND(SUM(CASE WHEN status = 'failed' THEN amount_ngn ELSE 0 END), 2) AS failed_volume_ngn
    FROM transactions
    GROUP BY gateway
)
SELECT
    gateway,
    total_tx,
    ROUND(100.0 * success_tx / total_tx, 2) AS success_rate_pct,
    ROUND(100.0 * failed_tx / total_tx, 2) AS failure_rate_pct,
    ROUND(100.0 * pending_tx / total_tx, 2) AS pending_rate_pct,
    ROUND(100.0 * reversed_tx / total_tx, 2) AS reversed_rate_pct,
    avg_amount_ngn,
    failed_volume_ngn
FROM gateway_stats
ORDER BY failure_rate_pct DESC;

-- name: 03_revenue_by_service
WITH svc AS (
    SELECT
        service,
        COUNT(*) AS success_tx,
        ROUND(SUM(amount_ngn), 2) AS gmv_ngn,
        ROUND(SUM(fee_ngn), 2) AS fee_revenue_ngn,
        ROUND(AVG(amount_ngn), 2) AS avg_ticket_ngn
    FROM transactions
    WHERE status = 'success'
    GROUP BY service
)
SELECT
    service,
    success_tx,
    gmv_ngn,
    ROUND(100.0 * gmv_ngn / SUM(gmv_ngn) OVER (), 2) AS gmv_share_pct,
    fee_revenue_ngn,
    ROUND(100.0 * fee_revenue_ngn / SUM(fee_revenue_ngn) OVER (), 2) AS fee_share_pct,
    avg_ticket_ngn
FROM svc
ORDER BY fee_revenue_ngn DESC;

-- name: 04_monthly_volume_and_mom_growth
WITH monthly AS (
    SELECT
        strftime('%Y-%m', created_at) AS month,
        COUNT(*) AS total_tx,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_tx,
        ROUND(SUM(CASE WHEN status = 'success' THEN amount_ngn ELSE 0 END), 2) AS gmv_ngn,
        ROUND(SUM(fee_ngn), 2) AS fee_revenue_ngn
    FROM transactions
    GROUP BY strftime('%Y-%m', created_at)
)
SELECT
    month,
    total_tx,
    success_tx,
    gmv_ngn,
    fee_revenue_ngn,
    ROUND(
        100.0 * (total_tx - LAG(total_tx) OVER (ORDER BY month))
        / NULLIF(LAG(total_tx) OVER (ORDER BY month), 0),
        2
    ) AS mom_tx_growth_pct
FROM monthly
ORDER BY month;

-- name: 05_worst_gateway_outage_days
WITH daily_gw AS (
    SELECT
        DATE(created_at) AS tx_date,
        gateway,
        COUNT(*) AS total_tx,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_tx,
        ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) AS failure_rate_pct
    FROM transactions
    GROUP BY DATE(created_at), gateway
    HAVING COUNT(*) >= 20
),
ranked AS (
    SELECT
        tx_date,
        gateway,
        total_tx,
        failed_tx,
        failure_rate_pct,
        RANK() OVER (ORDER BY failure_rate_pct DESC) AS failure_rank
    FROM daily_gw
)
SELECT tx_date, gateway, total_tx, failed_tx, failure_rate_pct, failure_rank
FROM ranked
WHERE failure_rank <= 5
ORDER BY failure_rank, tx_date;

-- name: 06_peak_hours
SELECT
    CAST(strftime('%H', created_at) AS INTEGER) AS hour_of_day,
    COUNT(*) AS total_tx,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_daily_tx,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) AS failure_rate_pct
FROM transactions
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- name: 07_weekend_and_monthend_lift
WITH tagged AS (
    SELECT
        DATE(created_at) AS tx_date,
        CASE WHEN CAST(strftime('%w', created_at) AS INTEGER) IN (0, 5, 6) THEN 'Fri-Sun' ELSE 'Mon-Thu' END AS week_part,
        CASE WHEN CAST(strftime('%d', created_at) AS INTEGER) >= 25 THEN 'Month-End (25-31)' ELSE 'Days 1-24' END AS month_part,
        COUNT(*) AS daily_tx,
        ROUND(SUM(CASE WHEN status = 'success' THEN amount_ngn ELSE 0 END), 2) AS daily_gmv_ngn
    FROM transactions
    GROUP BY DATE(created_at)
)
SELECT
    week_part,
    month_part,
    COUNT(*) AS num_days,
    ROUND(AVG(daily_tx), 1) AS avg_daily_tx,
    ROUND(AVG(daily_gmv_ngn), 2) AS avg_daily_gmv_ngn
FROM tagged
GROUP BY week_part, month_part
ORDER BY avg_daily_tx DESC;

-- name: 08_duplicate_charge_anomalies
WITH ordered_success AS (
    SELECT
        tx_id,
        user_id,
        service,
        gateway,
        amount_ngn,
        created_at,
        LAG(tx_id) OVER (
            PARTITION BY user_id, service, amount_ngn
            ORDER BY created_at, tx_id
        ) AS prev_tx_id,
        LAG(created_at) OVER (
            PARTITION BY user_id, service, amount_ngn
            ORDER BY created_at, tx_id
        ) AS prev_created_at
    FROM transactions
    WHERE status = 'success'
),
flagged AS (
    SELECT
        prev_tx_id,
        tx_id AS duplicate_tx_id,
        user_id,
        service,
        gateway,
        amount_ngn,
        prev_created_at,
        created_at AS dup_created_at,
        CAST((julianday(created_at) - julianday(prev_created_at)) * 86400 AS INTEGER) AS seconds_apart
    FROM ordered_success
    WHERE prev_created_at IS NOT NULL
      AND (julianday(created_at) - julianday(prev_created_at)) * 86400 <= 120
)
SELECT
    COUNT(*) AS duplicate_pairs_detected,
    ROUND(SUM(amount_ngn), 2) AS duplicate_exposure_ngn,
    ROUND(AVG(seconds_apart), 1) AS avg_seconds_apart
FROM flagged;

-- name: 09_duplicate_charge_samples
WITH ordered_success AS (
    SELECT
        tx_id,
        user_id,
        service,
        gateway,
        amount_ngn,
        created_at,
        LAG(tx_id) OVER (
            PARTITION BY user_id, service, amount_ngn
            ORDER BY created_at, tx_id
        ) AS prev_tx_id,
        LAG(created_at) OVER (
            PARTITION BY user_id, service, amount_ngn
            ORDER BY created_at, tx_id
        ) AS prev_created_at
    FROM transactions
    WHERE status = 'success'
)
SELECT
    prev_tx_id,
    tx_id AS duplicate_tx_id,
    user_id,
    service,
    gateway,
    amount_ngn,
    CAST((julianday(created_at) - julianday(prev_created_at)) * 86400 AS INTEGER) AS seconds_apart
FROM ordered_success
WHERE prev_created_at IS NOT NULL
  AND (julianday(created_at) - julianday(prev_created_at)) * 86400 <= 120
ORDER BY amount_ngn DESC
LIMIT 10;

-- name: 10_retention_cohorts
WITH user_cohorts AS (
    SELECT
        user_id,
        strftime('%Y-%m', signup_date) AS cohort_month,
        (CAST(strftime('%Y', signup_date) AS INTEGER) * 12 + CAST(strftime('%m', signup_date) AS INTEGER)) AS cohort_idx
    FROM users
),
activity AS (
    SELECT DISTINCT
        t.user_id,
        uc.cohort_month,
        (CAST(strftime('%Y', t.created_at) AS INTEGER) * 12 + CAST(strftime('%m', t.created_at) AS INTEGER)) - uc.cohort_idx AS month_offset
    FROM transactions t
    JOIN user_cohorts uc ON uc.user_id = t.user_id
    WHERE t.status = 'success'
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_users
    FROM user_cohorts
    GROUP BY cohort_month
)
SELECT
    a.cohort_month,
    cs.cohort_users,
    a.month_offset,
    COUNT(DISTINCT a.user_id) AS retained_users,
    ROUND(100.0 * COUNT(DISTINCT a.user_id) / cs.cohort_users, 1) AS retention_pct
FROM activity a
JOIN cohort_sizes cs ON cs.cohort_month = a.cohort_month
WHERE a.cohort_month <= '2025-07'
  AND a.month_offset BETWEEN 0 AND 5
GROUP BY a.cohort_month, cs.cohort_users, a.month_offset
ORDER BY a.cohort_month, a.month_offset;

-- name: 11_top_users_spend_share
WITH user_spend AS (
    SELECT
        t.user_id,
        u.kyc_tier,
        COUNT(*) AS success_tx,
        ROUND(SUM(t.amount_ngn), 2) AS total_spend_ngn
    FROM transactions t
    JOIN users u ON u.user_id = t.user_id
    WHERE t.status = 'success'
    GROUP BY t.user_id, u.kyc_tier
),
ranked AS (
    SELECT
        user_id,
        kyc_tier,
        success_tx,
        total_spend_ngn,
        ROUND(100.0 * total_spend_ngn / SUM(total_spend_ngn) OVER (), 3) AS share_pct,
        ROW_NUMBER() OVER (ORDER BY total_spend_ngn DESC) AS spend_rank
    FROM user_spend
)
SELECT spend_rank, user_id, kyc_tier, success_tx, total_spend_ngn, share_pct
FROM ranked
WHERE spend_rank <= 10
ORDER BY spend_rank;

-- name: 12_high_value_failure_impact
SELECT
    gateway,
    COUNT(*) AS high_val_tx,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_high_val_tx,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) AS high_val_fail_pct,
    ROUND(SUM(CASE WHEN status = 'failed' THEN amount_ngn ELSE 0 END), 2) AS failed_high_val_ngn
FROM transactions
WHERE amount_ngn >= 20000
GROUP BY gateway
ORDER BY failed_high_val_ngn DESC;
