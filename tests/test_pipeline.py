"""Automated verification tests for the fintech-transactions-analysis pipeline."""

from pathlib import Path
import sqlite3

from scripts.generate_data import generate_dataset, BASE_TRANSACTIONS, DUPLICATE_ANOMALIES
from scripts.analyze import run_analysis


def test_end_to_end_reproducible_pipeline(tmp_path: Path):
    # Copy SQL file into a temp project layout so tests don't mutate repo outputs
    repo_root = Path(__file__).resolve().parent.parent
    (tmp_path / "sql").mkdir()
    (tmp_path / "sql" / "queries.sql").write_text(
        (repo_root / "sql" / "queries.sql").read_text(encoding="utf-8"), encoding="utf-8"
    )

    summary = generate_dataset(tmp_path / "data", seed=42)
    assert summary["transactions"] == BASE_TRANSACTIONS + DUPLICATE_ANOMALIES

    results = run_analysis(tmp_path)
    assert len(results) == 12

    # Outage window on GatewayBeta (Aug 14-15, 2025) must appear in top failure days
    worst = results["05_worst_gateway_outage_days"]
    assert any(
        row["gateway"] == "GatewayBeta" and row["tx_date"] in ("2025-08-14", "2025-08-15")
        for _, row in worst.iterrows()
    )

    # Duplicate-charge query must detect at least the injected anomalies
    dups = results["08_duplicate_charge_anomalies"]
    assert int(dups.iloc[0]["duplicate_pairs_detected"]) >= DUPLICATE_ANOMALIES

    # All 5 charts must exist and be non-empty
    charts = list((tmp_path / "outputs" / "charts").glob("*.png"))
    assert len(charts) == 5
    assert all(c.stat().st_size > 10_000 for c in charts)
