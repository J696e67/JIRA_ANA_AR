"""
invoice_routes.py
All HTTP endpoints: upload, preview, download, send-email, send-all, index.
Each endpoint validates input, delegates to services, returns JSON or file.
"""
import os
import tempfile
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from config import HOURLY_RATE
from services.csv_service import load_csv_rows
from services.email_service import make_email_body, send_all_emails, send_invoice_email
from services.invoice_service import generate_invoice, _ordinal_date
from utils.session_store import get_session, store_session

invoice_bp = Blueprint("invoice", __name__)


@invoice_bp.route("/")
def index():
    return render_template("index.html")


@invoice_bp.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "File must be a CSV"}), 400

    session_id = str(uuid.uuid4())
    output_dir = tempfile.mkdtemp(prefix=f"invoices_{session_id[:8]}_")

    content = f.read().decode("utf-8-sig")
    if not content.strip():
        return jsonify({"error": "Empty or invalid CSV"}), 400

    try:
        rows = load_csv_rows(content, output_dir)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Preprocessing failed: {e}"}), 500

    session_data = {}
    all_rows = []

    for row in rows:
        row = {k.strip(): v for k, v in row.items() if k}
        invoice_id = str(uuid.uuid4())
        issue_key = row.get("issue_key", "").strip()
        send_flag = row.get("send_invoice", "").strip().lower()

        entry = {
            "invoice_id": invoice_id,
            "row": row,
            "pdf_path": None,
            "status": "pending",
            "error": None,
            "email_status": None,
        }

        if send_flag == "yes":
            ok = generate_invoice(row, output_dir)
            if ok:
                pdf_path = os.path.join(output_dir, f"CONSOLIDATED INVOICE_{issue_key}.pdf")
                entry["pdf_path"] = pdf_path
                entry["status"] = "generated"
            else:
                entry["status"] = "error"
                entry["error"] = "PDF generation failed (check required fields)"
        else:
            entry["status"] = "skipped"

        session_data[invoice_id] = entry

        hours = None
        try:
            hours = float(row.get("quote", ""))
        except (ValueError, TypeError):
            pass

        all_rows.append({
            "invoice_id": invoice_id,
            "issue_key": issue_key,
            "pi_name": row.get("pi_name", "").strip(),
            "summary": row.get("summary", "").strip(),
            "hours": hours,
            "amount": round(hours * HOURLY_RATE, 2) if hours is not None else None,
            "created": row.get("created", "").strip(),
            "fund_number": row.get("fund_number", "").strip(),
            "send_invoice": send_flag,
            "status": entry["status"],
            "error": entry["error"],
            "email_status": entry["email_status"],
            "email_subject": f"{issue_key} INVOICE {_ordinal_date(datetime.now())}",
            "email_body": make_email_body(row) if send_flag == "yes" else None,
        })

    store_session(session_id, {"output_dir": output_dir, "data": session_data})

    return jsonify({"session_id": session_id, "invoices": all_rows})


@invoice_bp.route("/preview/<session_id>/<invoice_id>")
def preview(session_id, invoice_id):
    session = get_session(session_id)
    if not session:
        return "Session not found", 404
    entry = session["data"].get(invoice_id)
    if not entry or not entry["pdf_path"]:
        return "Invoice not found or not generated", 404
    return send_file(entry["pdf_path"], mimetype="application/pdf")


@invoice_bp.route("/send-email", methods=["POST"])
def send_email():
    data = request.json or {}
    session_id = data.get("session_id")
    invoice_id = data.get("invoice_id")
    from_addr = data.get("from_addr", "").strip()
    password = data.get("password", "")
    to_addr = data.get("to_addr", "").strip()
    cc_addr = data.get("cc_addr", "").strip()
    subject = data.get("subject", "")
    body = data.get("body", "")

    if not from_addr or not password:
        return jsonify({"error": "From address and password are required"}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    entry = session["data"].get(invoice_id)
    if not entry or not entry["pdf_path"]:
        return jsonify({"error": "Invoice not found or not generated"}), 404

    try:
        send_invoice_email(from_addr, password, to_addr, cc_addr, subject, body, entry["pdf_path"])
        entry["email_status"] = "sent"
        return jsonify({"success": True})
    except Exception as e:
        entry["email_status"] = "error"
        return jsonify({"error": str(e)}), 500


@invoice_bp.route("/send-all", methods=["POST"])
def send_all():
    data = request.json or {}
    session_id = data.get("session_id")
    from_addr = data.get("from_addr", "").strip()
    password = data.get("password", "")
    to_addr = data.get("to_addr", "").strip()
    cc_addr = data.get("cc_addr", "").strip()

    if not from_addr or not password:
        return jsonify({"error": "From address and password are required"}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    try:
        results = send_all_emails(session["data"], from_addr, password, to_addr, cc_addr)
    except Exception as e:
        return jsonify({"error": f"SMTP login failed: {e}"}), 500

    return jsonify({"results": results})
