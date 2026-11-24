"""Generate a deterministic synthetic dataset of NGN wallet & bill-payment transactions.

Personal portfolio project. All users, gateways, and transactions are 100% synthetic.
"""

from __future__ import annotations

import csv
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
NUM_USERS = 2500
BASE_TRANSACTIONS = 50000
DUPLICATE_ANOMALIES = 48

START_DATE = datetime(2025, 1, 1, 0, 0, 0)
END_DATE = datetime(2025, 12, 31, 23, 59, 59)

# Simulated GatewayBeta outage window (30 hours in mid-August 2025)
OUTAGE_START = datetime(2025, 8, 14, 9, 0, 0)
OUTAGE_END = datetime(2025, 8, 15, 15, 0, 0)

SERVICES = [
    # (name, weight, min_ngn, max_ngn, fee_rate_or_flat)
    ("airtime", 0.30, 100, 5000, ("pct", 0.015)),
    ("data", 0.28, 300, 15000, ("pct", 0.020)),
    ("transfers", 0.22, 1000, 150000, ("flat", 25.0)),
    ("electricity", 0.12, 2000, 45000, ("flat", 100.0)),
    ("cable_tv", 0.08, 3300, 35000, ("flat", 100.0)),
]

GATEWAYS = [
    # (name, weight, base_success, base_failed, base_pending, base_reversed)
    ("GatewayAlpha", 0.45, 0.945, 0.035, 0.010, 0.010),
    ("GatewayBeta", 0.33, 0.905, 0.065, 0.018, 0.012),
    ("GatewayGamma", 0.22, 0.928, 0.048, 0.014, 0.010),
]

# Hourly traffic weights (0..23): quiet overnight, peak midday through early evening
HOUR_WEIGHTS = [
    0.8, 0.5, 0.4, 0.4, 0.6, 1.2, 2.5, 4.2,
    6.0, 6.8, 7.2, 7.5, 8.2, 8.0, 7.6, 7.4,
    7.8, 8.4, 8.0, 7.0, 5.5, 3.8, 2.4, 1.4,
]


def _pick_weighted(rng: random.Random, items: list, weights: list[float]):
    return rng.choices(items, weights=weights, k=1)[0]


def _sample_amount(rng: random.Random, service_name: str, low: int, high: int) -> float:
    # Right-skewed realistic amounts rounded to neat NGN increments
    raw = low + (high - low) * (rng.random() ** 2.2)
    step = 50 if service_name in ("airtime", "data") else 100
    return float(max(low, round(raw / step) * step))


def _compute_fee(amount: float, fee_spec: tuple[str, float]) -> float:
    kind, val = fee_spec
    if kind == "pct":
        return round(amount * val, 2)
    return float(val)


def generate_dataset(data_dir: Path, seed: int = SEED) -> dict:
    """Generate synthetic users and transactions, saving both CSV and SQLite."""
    data_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    # 1. Generate synthetic users with staggered signup dates across 2025 (weighted earlier)
    users = []
    signup_days_pool = list(range(0, 365))
    signup_weights = [max(0.2, 1.5 - (d / 365.0)) for d in signup_days_pool]

    for uid in range(1, NUM_USERS + 1):
        day_offset = _pick_weighted(rng, signup_days_pool, signup_weights)
        signup_dt = START_DATE + timedelta(
            days=day_offset,
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        tier = _pick_weighted(rng, ["tier_1", "tier_2", "tier_3"], [0.55, 0.32, 0.13])
        # Retention propensity so cohorts decay realistically
        retention_months = _pick_weighted(
            rng, [1, 2, 3, 5, 8, 12], [0.22, 0.16, 0.14, 0.15, 0.15, 0.18]
        )
        users.append(
            {
                "user_id": f"USR-{uid:05d}",
                "signup_date": signup_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "signup_dt": signup_dt,
                "active_until": min(END_DATE, signup_dt + timedelta(days=retention_months * 30)),
                "kyc_tier": tier,
                "activity_weight": rng.uniform(0.3, 3.0) * (1.8 if tier == "tier_3" else 1.0),
            }
        )

    user_weights = [u["activity_weight"] for u in users]
    service_names = [s[0] for s in SERVICES]
    service_weights = [s[1] for s in SERVICES]
    service_map = {s[0]: s for s in SERVICES}

    gateway_names = [g[0] for g in GATEWAYS]
    gateway_weights = [g[1] for g in GATEWAYS]
    gateway_map = {g[0]: g for g in GATEWAYS}
    hours = list(range(24))

    # Build day weights across 2025: weekend boost + month-end boost
    all_days = [START_DATE + timedelta(days=i) for i in range(365)]
    day_weights = []
    for d in all_days:
        w = 1.0
        if d.weekday() in (4, 5, 6):  # Fri, Sat, Sun
            w *= 1.22
        if d.day >= 25:  # Month-end salary & bill-pay surge
            w *= 1.35
        day_weights.append(w)

    transactions = []
    tx_counter = 1

    for _ in range(BASE_TRANSACTIONS):
        user = _pick_weighted(rng, users, user_weights)
        # Pick a day within the user's active lifecycle
        for _attempt in range(10):
            day = _pick_weighted(rng, all_days, day_weights)
            if user["signup_dt"].date() <= day.date() <= user["active_until"].date():
                break
        else:
            span = max(1, (user["active_until"] - user["signup_dt"]).days)
            day = user["signup_dt"] + timedelta(days=rng.randint(0, span))

        hour = _pick_weighted(rng, hours, HOUR_WEIGHTS)
        created_dt = datetime(
            day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59)
        )
        if created_dt < user["signup_dt"]:
            created_dt = user["signup_dt"] + timedelta(minutes=rng.randint(1, 59))
        if created_dt > END_DATE:
            created_dt = END_DATE

        svc_name = _pick_weighted(rng, service_names, service_weights)
        _, _, low, high, fee_spec = service_map[svc_name]
        amount = _sample_amount(rng, svc_name, low, high)
        fee = _compute_fee(amount, fee_spec)

        gw_name = _pick_weighted(rng, gateway_names, gateway_weights)
        _, _, p_ok, p_fail, p_pend, p_rev = gateway_map[gw_name]

        # Apply simulated GatewayBeta outage window
        if gw_name == "GatewayBeta" and OUTAGE_START <= created_dt <= OUTAGE_END:
            p_ok, p_fail, p_pend, p_rev = 0.22, 0.68, 0.08, 0.02

        status = _pick_weighted(
            rng, ["success", "failed", "pending", "reversed"], [p_ok, p_fail, p_pend, p_rev]
        )

        transactions.append(
            {
                "tx_id": f"TXN-{tx_counter:06d}",
                "user_id": user["user_id"],
                "service": svc_name,
                "gateway": gw_name,
                "status": status,
                "amount_ngn": amount,
                "fee_ngn": fee if status == "success" else 0.0,
                "created_at": created_dt.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        tx_counter += 1

    # 2. Inject realistic duplicate-charge anomalies (retry / race-condition double debits)
    successful_txs = [t for t in transactions if t["status"] == "success"]
    anomaly_sources = rng.sample(successful_txs, k=DUPLICATE_ANOMALIES)
    for src in anomaly_sources:
        orig_dt = datetime.strptime(src["created_at"], "%Y-%m-%d %H:%M:%S")
        dup_dt = min(END_DATE, orig_dt + timedelta(seconds=rng.randint(3, 75)))
        transactions.append(
            {
                "tx_id": f"TXN-{tx_counter:06d}",
                "user_id": src["user_id"],
                "service": src["service"],
                "gateway": src["gateway"],
                "status": "success",
                "amount_ngn": src["amount_ngn"],
                "fee_ngn": src["fee_ngn"],
                "created_at": dup_dt.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        tx_counter += 1

    # Sort chronologically
    transactions.sort(key=lambda r: (r["created_at"], r["tx_id"]))

    # Save CSV
    csv_path = data_dir / "transactions.csv"
    fieldnames = [
        "tx_id",
        "user_id",
        "service",
        "gateway",
        "status",
        "amount_ngn",
        "fee_ngn",
        "created_at",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(transactions)

    # Load into SQLite
    db_path = data_dir / "fintech_transactions.sqlite"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            signup_date TEXT NOT NULL,
            kyc_tier TEXT NOT NULL
        );

        CREATE TABLE transactions (
            tx_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            service TEXT NOT NULL,
            gateway TEXT NOT NULL,
            status TEXT NOT NULL,
            amount_ngn REAL NOT NULL,
            fee_ngn REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE INDEX idx_tx_created_at ON transactions(created_at);
        CREATE INDEX idx_tx_gateway_status ON transactions(gateway, status);
        CREATE INDEX idx_tx_user_service_amount ON transactions(user_id, service, amount_ngn, created_at);
        """
    )

    cur.executemany(
        "INSERT INTO users (user_id, signup_date, kyc_tier) VALUES (?, ?, ?)",
        [(u["user_id"], u["signup_date"], u["kyc_tier"]) for u in users],
    )
    cur.executemany(
        """
        INSERT INTO transactions (
            tx_id, user_id, service, gateway, status, amount_ngn, fee_ngn, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                t["tx_id"],
                t["user_id"],
                t["service"],
                t["gateway"],
                t["status"],
                t["amount_ngn"],
                t["fee_ngn"],
                t["created_at"],
            )
            for t in transactions
        ],
    )
    conn.commit()
    conn.close()

    return {
        "users": len(users),
        "transactions": len(transactions),
        "injected_duplicates": DUPLICATE_ANOMALIES,
        "csv_path": str(csv_path),
        "db_path": str(db_path),
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    summary = generate_dataset(root / "data")
    print(f"Generated synthetic dataset (seed={SEED}): {summary}")
