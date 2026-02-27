"""
email_service.py
SMTP connection, build email with attachment, send.
Pure functions — no Flask dependencies.
"""
import os
import re
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT


def make_email_body(row: dict) -> str:
    """Build the standard invoice email body from a row dict."""
    issue_key = row.get("issue_key", "").strip()
    pi_name = row.get("pi_name", "").strip()
    pi_display = re.sub(r"^Dr\.?\s*", "", pi_name)
    summary = row.get("summary", "").strip()
    fund_number = row.get("fund_number", "n/a").strip() or "n/a"

    from services.invoice_service import _ordinal_date
    from datetime import datetime
    date_str = _ordinal_date(datetime.now())

    return (
        f"Hi Dr. {pi_display},\n"
        f"\n"
        f"Please find attached invoice for ticket {issue_key}: \"{summary}\".\n"
        f"\n"
        f"We will submit the journal entry using the fund number you provided ({fund_number}).\n"
        f"\n"
        f"No action is needed on your part\u2014the entry will be processed automatically on our end.\n"
        f"\n"
        f"Please let us know if you have any questions.\n"
        f"\n"
        f"Thank you,\n"
        f"Jing Yang, PhD\n"
        f"Applications Analyst, Epic Research Reporting\n"
        f"Enterprise Data Services\n"
        f"Digital and Technology Partners\n"
        f"Mount Sinai Health System\n"
    )


def send_invoice_email(
    from_addr: str,
    password: str,
    to_addr: str,
    cc_addr: str,
    subject: str,
    body: str,
    pdf_path: str,
) -> bool:
    """
    Send a single invoice email with the PDF attached.

    Returns True on success, raises on failure.
    """
    smtp_conn = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    smtp_conn.starttls()
    smtp_conn.login(from_addr, password)

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Cc"] = cc_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as f:
        pdf_part = MIMEApplication(f.read(), _subtype="pdf")
        pdf_part.add_header(
            "Content-Disposition", "attachment",
            filename=os.path.basename(pdf_path),
        )
        msg.attach(pdf_part)

    recipients = [addr for addr in [to_addr, cc_addr] if addr]
    smtp_conn.sendmail(from_addr, recipients, msg.as_string())
    smtp_conn.quit()
    return True


def send_all_emails(
    session_data: dict,
    from_addr: str,
    password: str,
    to_addr: str,
    cc_addr: str,
) -> list[dict]:
    """
    Send emails for all 'generated' invoices in a session.

    Returns a list of result dicts: [{invoice_id, success, error?}, ...]
    """
    from services.invoice_service import _ordinal_date
    from datetime import datetime

    smtp_conn = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    smtp_conn.starttls()
    smtp_conn.login(from_addr, password)

    results = []
    for invoice_id, entry in session_data.items():
        if entry["status"] != "generated":
            continue

        row = entry["row"]
        issue_key = row.get("issue_key", "").strip()
        subject = f"{issue_key} INVOICE {_ordinal_date(datetime.now())}"
        body = make_email_body(row)

        try:
            msg = MIMEMultipart()
            msg["From"] = from_addr
            msg["To"] = to_addr
            msg["Cc"] = cc_addr
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with open(entry["pdf_path"], "rb") as f:
                pdf_part = MIMEApplication(f.read(), _subtype="pdf")
                pdf_part.add_header(
                    "Content-Disposition", "attachment",
                    filename=os.path.basename(entry["pdf_path"]),
                )
                msg.attach(pdf_part)

            recipients = [addr for addr in [to_addr, cc_addr] if addr]
            smtp_conn.sendmail(from_addr, recipients, msg.as_string())
            entry["email_status"] = "sent"
            results.append({"invoice_id": invoice_id, "success": True})
        except Exception as e:
            entry["email_status"] = "error"
            results.append({"invoice_id": invoice_id, "success": False, "error": str(e)})

    smtp_conn.quit()
    return results
