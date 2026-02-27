"""
csv_service.py
CSV reading, format detection, cleaning, column renaming, send_invoice flag.
Pure functions — no Flask dependencies.
"""
from __future__ import annotations

import csv
import os
import re
from io import StringIO

import numpy as np
import pandas as pd


# ── Column Mapping ──────────────────────────────────────────────────────────

RAW_TO_CLEAN = {
    "Custom field (Account)": "account",
    "Custom field (Name of PI)": "pi_name",
    "Custom field (Are you requesting a custom report or a PHI list?)": "custom_report_or_phi",
    "Custom field (Brief Description of Data Request Purpose)": "data_request_purpose",
    "Custom field (Request Type)": "request_type",
    "Custom field (Date range for patient/visit inclusion)": "date_range",
    "Custom field (Date range criteria based on VISITS (IP, OP, ED, all) / other (specify))": "date_range_2",
    "Custom field (Department Name)": "department",
    "Custom field (Do you need PHI in this report/data set?)": "phi",
    "Custom field (Externally Funded Research)": "external_fund",
    "Custom field (Fund Number)": "fund_number",
    "Custom field (Funding Source)": "fund_source",
    "Custom field (IRB #)": "irb_num",
    "Custom field (Invoice Paid)": "invoice_paid",
    "Custom field (Is this request for IRB Approved Research or QI?)": "irb_or_qi",
    "Custom field (Patient Exclusion Criteria)": "exclusion",
    "Custom field (Is this a cancer related study?)": "cancer_related",
    "Custom field (Are you a CTSA-funded trainee TL1/KL2 (Scholar research program)?)": "ctsa_trainee_tl1kl2",
    "Custom field (Are you a mentored K23/K08/T32 (Mentored career development program)?)": "career_develop_program",
    "Custom field (Are you a PORTAL (MD/MSCR) student?)": "portal_student",
    "Custom field (Patient Inclusion Criteria)": "inclusion",
    "Custom field (Provide Data or Cost Estimate)": "costes_or_datarequest",
    "Custom field (Report Fields)": "report_fields",
    "Custom field (Requestor Name)": "req_name",
    "Custom field (Requestor Title)": "req_title",
    "Custom field (Estimated hours quoted to customer)": "quote",
    "Custom field (Ticket History)": "ticket_history",
    "Custom field (IRB Expiration Date)": "irb_expire_date",
    "Security Level": "security_level",
    "Issue Type": "issue_type",
    "Labels": "label_1",
    "Time Spent": "time_spent",
}

# Final columns to keep (after all processing) → clean name
FINAL_COLUMNS = {
    "Issue key": "issue_key",
    "Summary": "summary",
    "description": "description",          # computed column
    "Status": "status",
    "Resolution": "sesolution",
    "quote": "quote",
    "pi_name": "pi_name",
    "fund_number": "fund_number",
    "costes_or_datarequest": "costes_or_datarequest",
    "inclusion": "inclusion",
    "exclusion": "exclusion",
    "report_fields": "report_fields",
    "irb_or_qi": "irb_or_qi",
    "irb_num": "irb_num",
    "phi": "phi",
    "Resolved": "resolved",
    "Created": "created",
    "Updated": "updated",
    "Assignee": "assignee",
    "Assignee Id": "assignee_id",
    "Creator": "creater",
    "Creator Id": "creater_id",
    "Reporter": "reporter",
    "Reporter Id": "reporter_id",
    "request_type": "request_type",
    "department": "department",
    "last_comment_by": "last_comment_by",   # computed column
    "last_comment": "last_comment",         # computed column
    "send_invoice": "send_invoice",         # computed: "yes" if quote > 0
}


# ── Helper Functions ────────────────────────────────────────────────────────

def _get_sorted_columns(df: pd.DataFrame, prefix: str) -> list[str]:
    """Return columns matching a prefix, sorted numerically."""
    cols = [c for c in df.columns if c.startswith(prefix)]
    return sorted(
        cols,
        key=lambda c: int(m.group(1)) if (m := re.search(rf"{prefix}(?:\.(\d+))?$", c)) and m.group(1) else 0,
    )


def _extract_ticket_notes(row: pd.Series, attachment_cols: list[str]) -> str | None:
    """Find attachment filenames that match '<Issue key>*.xlsx'."""
    issue_key = str(row["Issue key"])
    pattern = re.compile(rf"{re.escape(issue_key)}.*\.xlsx")
    matches = set()
    for col in attachment_cols:
        val = row[col]
        if pd.notna(val):
            matches.update(pattern.findall(str(val)))
    return "; ".join(sorted(matches)) if matches else None


def _last_non_empty_comment(row: pd.Series, comment_cols: list[str]) -> str | None:
    """Return the last non-empty comment value."""
    for col in reversed(comment_cols):
        val = row[col]
        if pd.notna(val) and str(val).strip():
            return val
    return None


def _extract_commenter(text) -> str | None:
    """Extract the author name from a JIRA comment string (second semicolon-delimited field)."""
    if pd.isna(text):
        return None
    parts = text.split(";", 2)
    return parts[1].strip() if len(parts) >= 2 else None


def _merge_description_fields(df: pd.DataFrame) -> pd.Series:
    """Combine Description + data_request_purpose + Project description into one field."""
    merge_cols = ["Description", "data_request_purpose", "Project description"]
    existing = [c for c in merge_cols if c in df.columns]
    return (
        df[existing]
        .fillna("")
        .astype(str)
        .apply(lambda row: " ".join(s for s in (v.strip() for v in row) if s), axis=1)
    )


# ── Main Processing Functions ───────────────────────────────────────────────

def preprocess_csv(input_path: str, output_path: str | None = None) -> pd.DataFrame:
    """
    Read a raw JIRA CSV export and return a cleaned DataFrame
    ready for invoice generation.

    Parameters
    ----------
    input_path : str
        Path to the raw CSV file.
    output_path : str | None
        If provided, save the cleaned CSV to this path.

    Returns
    -------
    pd.DataFrame
        Cleaned and reshaped DataFrame.
    """
    # 1. Load & rename raw columns
    raw_df = pd.read_csv(input_path)
    raw_df.rename(columns=RAW_TO_CLEAN, inplace=True)

    # 2. Basic type conversions & fills
    raw_df["fund_source"] = raw_df.get("fund_source", pd.Series(dtype=str)).fillna("")
    raw_df["fund_number"] = raw_df.get("fund_number", pd.Series(dtype=str)).fillna("")
    raw_df["new_fund_number"] = raw_df["fund_number"].astype(str) + " " + raw_df["fund_source"]

    for date_col in ["Created", "Resolved"]:
        if date_col in raw_df.columns:
            raw_df[date_col] = pd.to_datetime(raw_df[date_col], errors="coerce")

    for text_col in ["Summary", "Description", "data_request_purpose", "pi_name"]:
        if text_col in raw_df.columns:
            raw_df[text_col] = raw_df[text_col].fillna("")

    # 3. Compute derived columns
    attachment_cols = _get_sorted_columns(raw_df, "Attachment")
    comment_cols = _get_sorted_columns(raw_df, "Comment")

    raw_df["ticket_note"] = raw_df.apply(
        _extract_ticket_notes, axis=1, attachment_cols=attachment_cols
    )
    raw_df["last_comment"] = raw_df.apply(
        _last_non_empty_comment, axis=1, comment_cols=comment_cols
    )
    raw_df["last_comment_by"] = raw_df["last_comment"].apply(_extract_commenter)
    raw_df["description"] = _merge_description_fields(raw_df)

    # 4. Compute send_invoice flag
    raw_df["send_invoice"] = (
        pd.to_numeric(raw_df.get("quote", 0), errors="coerce").fillna(0).gt(0)
        .map({True: "yes", False: "no"})
    )

    # 5. Select & rename final columns
    available = {k: v for k, v in FINAL_COLUMNS.items() if k in raw_df.columns}
    result_df = raw_df[list(available.keys())].rename(columns=available)

    # 6. Optionally save
    if output_path:
        result_df.to_csv(output_path, index=False)
        print(f"✅ Saved cleaned CSV → {output_path}  ({len(result_df)} rows)")

    return result_df


def load_csv_rows(content: str, output_dir: str) -> list[dict]:
    """
    Auto-detect CSV format and return a list of row dicts ready for invoice generation.

    - Raw JIRA export (any header starts with 'Custom field'): run preprocess_csv()
    - Clean format ('issue_key' present): pass through as-is
    - Unrecognized: raise ValueError
    """
    # Use csv.reader to correctly handle quoted column names
    first_row = next(csv.reader(StringIO(content)))
    headers = [h.strip() for h in first_row]

    is_jira_raw = any(h.startswith("Custom field") for h in headers)
    is_clean = "issue_key" in headers

    if not is_jira_raw and not is_clean:
        raise ValueError("Unrecognized CSV format")

    if is_jira_raw:
        print("[upload] Raw JIRA format detected → running preprocessor")
        tmp_path = os.path.join(output_dir, "_raw_upload.csv")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        df = preprocess_csv(tmp_path)

        # Convert date columns to strings _parse_created_date can handle
        for col in ("created", "resolved", "updated"):
            if col in df.columns:
                df[col] = (
                    pd.to_datetime(df[col], errors="coerce")
                    .dt.strftime("%m/%d/%Y")
                    .fillna("")
                )

        # Convert entire DataFrame to list of string dicts; replace NaN with ""
        rows = []
        for _, row_series in df.iterrows():
            row_dict = {}
            for col, val in row_series.items():
                if pd.isna(val) if not isinstance(val, str) else False:
                    row_dict[col] = ""
                else:
                    row_dict[col] = "" if str(val) == "nan" else str(val)
            rows.append(row_dict)
    else:
        print("[upload] Clean format detected → skipping preprocessor")
        reader = csv.DictReader(StringIO(content))
        reader.fieldnames = [n.strip() for n in reader.fieldnames]
        rows = [{k.strip(): v for k, v in row.items() if k} for row in reader]

    return rows
