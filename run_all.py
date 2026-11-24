"""Single entry point to reproduce synthetic data generation, SQL analysis, and charts."""

from pathlib import Path
from scripts.generate_data import generate_dataset
from scripts.analyze import run_analysis


def main() -> None:
    root = Path(__file__).resolve().parent
    gen_summary = generate_dataset(root / "data")
    print(f"[1/2] Generated dataset: {gen_summary['transactions']} transactions across {gen_summary['users']} users.")
    results = run_analysis(root)
    print(f"[2/2] Executed {len(results)} SQL queries and saved 5 charts to outputs/charts/.")


if __name__ == "__main__":
    main()
