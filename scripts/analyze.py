"""Run analytical SQL queries against SQLite and generate 5 matplotlib charts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def parse_named_queries(sql_path: Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    current_name: str | None = None
    buf: list[str] = []
    for line in sql_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name:"):
            if current_name and buf:
                queries[current_name] = "\n".join(buf).strip()
            current_name = line.split(":", 1)[1].strip()
            buf = []
        elif current_name is not None:
            buf.append(line)
    if current_name and buf:
        queries[current_name] = "\n".join(buf).strip()
    return queries


def run_analysis(root: Path) -> dict[str, pd.DataFrame]:
    db_path = root / "data" / "fintech_transactions.sqlite"
    sql_path = root / "sql" / "queries.sql"
    out_dir = root / "outputs"
    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    queries = parse_named_queries(sql_path)
    conn = sqlite3.connect(db_path)
    results: dict[str, pd.DataFrame] = {}
    serialized: dict[str, list[dict]] = {}

    for name, sql in queries.items():
        df = pd.read_sql_query(sql, conn)
        results[name] = df
        serialized[name] = df.to_dict(orient="records")

    # Daily gateway failure series for outage chart
    daily_gw = pd.read_sql_query(
        """
        SELECT
            DATE(created_at) AS tx_date,
            gateway,
            COUNT(*) AS total_tx,
            100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*) AS failure_rate_pct
        FROM transactions
        WHERE created_at BETWEEN '2025-08-01' AND '2025-08-31'
        GROUP BY DATE(created_at), gateway
        ORDER BY tx_date
        """,
        conn,
    )
    conn.close()

    (out_dir / "query_results.json").write_text(
        json.dumps(serialized, indent=2), encoding="utf-8"
    )

    # Save readable text summary
    summary_lines = []
    for name, df in results.items():
        summary_lines.append(f"=== {name} ===")
        summary_lines.append(df.to_string(index=False))
        summary_lines.append("")
    (out_dir / "summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")

    # Chart styling
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})

    # Chart 1: Gateway Failure Rates
    df_gw = results["02_failure_rate_by_gateway"]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    colors = ["#dc2626", "#f59e0b", "#2563eb"]
    bars = ax.bar(df_gw["gateway"], df_gw["failure_rate_pct"], color=colors[: len(df_gw)], width=0.55)
    ax.set_title("Transaction Failure Rate by Payment Gateway (2025 Synthetic Dataset)", fontweight="bold")
    ax.set_ylabel("Failure Rate (%)")
    ax.set_ylim(0, max(df_gw["failure_rate_pct"]) * 1.25)
    for bar, val in zip(bars, df_gw["failure_rate_pct"]):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.15, f"{val:.2f}%", ha="center", fontweight="bold")
    fig.tight_layout()
    fig.savefig(charts_dir / "01_gateway_failure_rates.png", dpi=150)
    plt.close(fig)

    # Chart 2: Fee Revenue & GMV by Service
    df_svc = results["03_revenue_by_service"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(df_svc["service"], df_svc["fee_revenue_ngn"] / 1_000_000, color="#0284c7", height=0.55)
    ax.invert_yaxis()
    ax.set_title("Fee Revenue by Service (NGN Millions, Successful Transactions)", fontweight="bold")
    ax.set_xlabel("Fee Revenue (NGN Millions)")
    ax.set_xlim(0, max(df_svc["fee_revenue_ngn"] / 1_000_000) * 1.22)
    for bar, val, share in zip(bars, df_svc["fee_revenue_ngn"] / 1_000_000, df_svc["fee_share_pct"]):
        ax.text(val + 0.02, bar.get_y() + bar.get_height() / 2, f"₦{val:.2f}M ({share:.1f}%)", va="center")
    fig.tight_layout()
    fig.savefig(charts_dir / "02_revenue_by_service.png", dpi=150)
    plt.close(fig)

    # Chart 3: August 2025 Daily Failure Rate (Outage Window)
    daily_gw["tx_date"] = pd.to_datetime(daily_gw["tx_date"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    gw_colors = {"GatewayAlpha": "#2563eb", "GatewayBeta": "#dc2626", "GatewayGamma": "#16a34a"}
    for gw, grp in daily_gw.groupby("gateway"):
        ax.plot(grp["tx_date"], grp["failure_rate_pct"], marker="o", markersize=3.5, label=gw, color=gw_colors.get(gw))
    ax.axvspan(pd.Timestamp("2025-08-14"), pd.Timestamp("2025-08-15"), color="#fee2e2", alpha=0.7, label="Outage Window")
    ax.set_title("August 2025 Daily Failure Rate by Gateway (Outage Spike Detected)", fontweight="bold")
    ax.set_ylabel("Daily Failure Rate (%)")
    ax.set_xlabel("Date (August 2025)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(charts_dir / "03_gateway_outage_august.png", dpi=150)
    plt.close(fig)

    # Chart 4: Hourly Transaction Volume
    df_hr = results["06_peak_hours"]
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.plot(df_hr["hour_of_day"], df_hr["total_tx"], color="#0f766e", marker="o", linewidth=2)
    ax.fill_between(df_hr["hour_of_day"], df_hr["total_tx"], color="#99f6e4", alpha=0.45)
    ax.set_title("Transaction Volume by Hour of Day (UTC/WAT)", fontweight="bold")
    ax.set_xlabel("Hour of Day (0–23)")
    ax.set_ylabel("Total Transactions")
    ax.set_xticks(range(0, 24, 2))
    fig.tight_layout()
    fig.savefig(charts_dir / "04_hourly_volume.png", dpi=150)
    plt.close(fig)

    # Chart 5: Retention Cohort Heatmap
    df_coh = results["10_retention_cohorts"]
    pivot = df_coh.pivot(index="cohort_month", columns="month_offset", values="retention_pct")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    im = ax.imshow(pivot.values, cmap="YlGnBu", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"M+{c}" for c in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_title("User Retention Cohorts (% Active with >=1 Successful Tx)", fontweight="bold")
    ax.set_xlabel("Months Since Signup")
    ax.set_ylabel("Signup Cohort")
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if pd.notna(val):
                color = "white" if val > 55 else "#111827"
                ax.text(j, i, f"{val:.1f}%", ha="center", va="center", color=color, fontsize=9)
    fig.colorbar(im, ax=ax, label="Retention (%)")
    fig.tight_layout()
    fig.savefig(charts_dir / "05_retention_cohorts.png", dpi=150)
    plt.close(fig)

    return results


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    run_analysis(root)
    print("Analysis complete. Outputs saved to outputs/.")
