#!/usr/bin/env python3
"""
scripts/generate_invoices.py
CLI entry point: preprocess CSV and generate PDF invoices.

Usage:
    python scripts/generate_invoices.py input.csv -o output_dir/
"""
import argparse
import csv
import os
import sys

# Allow imports from project root when run as: python scripts/generate_invoices.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.csv_service import preprocess_csv
from services.invoice_service import generate_invoice


def main():
    parser = argparse.ArgumentParser(
        description="Generate PDF invoices from a CSV file."
    )
    parser.add_argument("input", help="Path to CSV file (raw JIRA export or clean format)")
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directory for generated PDFs (default: same directory as input CSV)",
    )
    args = parser.parse_args()

    csv_path = args.input
    if not os.path.isfile(csv_path):
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(csv_path))
    os.makedirs(output_dir, exist_ok=True)

    # Detect format by checking headers
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        first_row = next(csv.reader(f))
    headers = [h.strip() for h in first_row]

    is_raw = any(h.startswith("Custom field") for h in headers)

    if is_raw:
        print(f"[CLI] Raw JIRA format detected → preprocessing...")
        df = preprocess_csv(csv_path)
        rows = []
        import pandas as pd
        for _, row_series in df.iterrows():
            row_dict = {}
            for col, val in row_series.items():
                if pd.isna(val) if not isinstance(val, str) else False:
                    row_dict[col] = ""
                else:
                    row_dict[col] = "" if str(val) == "nan" else str(val)
            rows.append(row_dict)
    else:
        print(f"[CLI] Clean format detected → reading directly...")
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [n.strip() for n in reader.fieldnames]
            rows = [{k.strip(): v for k, v in row.items() if k} for row in reader]

    generated = 0
    skipped = 0

    for row in rows:
        send_flag = row.get("send_invoice", "").strip().lower()
        if send_flag != "yes":
            skipped += 1
            continue

        issue_key = row.get("issue_key", "???").strip()
        print(f"Processing {issue_key}...")
        if generate_invoice(row, output_dir):
            generated += 1
        else:
            skipped += 1

    print(f"\nDone. Generated {generated} invoice(s), skipped {skipped} row(s).")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
