"""
triage_routes.py
HTTP endpoints for ticket triage: run, status, single re-triage.
Delegates all logic to triage_service; uses threading for background processing.
"""
import threading

from flask import Blueprint, jsonify, request

from services.triage_service import categorise_ticket, check_llm_available, load_team_members, triage_tickets
from utils.session_store import (
    get_session,
    get_triage,
    init_triage,
    set_triage_failed,
    store_triage_results,
    update_single_triage_result,
    update_triage_progress,
)

triage_bp = Blueprint("triage", __name__)


def _run_triage_worker(session_id: str, rows: list[dict]) -> None:
    """Background worker: triage every row and update session store."""
    def _progress(completed, total, current_key):
        update_triage_progress(session_id, completed, current_key)

    try:
        results = triage_tickets(rows, progress_callback=_progress)
        store_triage_results(session_id, results)
    except Exception as exc:
        set_triage_failed(session_id, str(exc))


@triage_bp.route("/triage", methods=["POST"])
def run_triage():
    """Start triage for all tickets in a session (runs in background thread)."""
    data = request.json or {}
    session_id = data.get("session_id")

    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Prevent concurrent triage runs
    existing = get_triage(session_id)
    if existing and existing["status"] == "processing":
        return jsonify({"error": "Triage already in progress"}), 409

    # Collect all rows from the session (including skipped invoices)
    rows = [entry["row"] for entry in session["data"].values()]
    if not rows:
        return jsonify({"error": "No ticket data in session"}), 400

    init_triage(session_id, len(rows))

    thread = threading.Thread(
        target=_run_triage_worker,
        args=(session_id, rows),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "processing", "total": len(rows)})


@triage_bp.route("/triage/llm-status")
def llm_status():
    """Return LLM availability for the sidebar status badge."""
    available = check_llm_available()
    return jsonify({"llm_available": available})


@triage_bp.route("/triage/status/<session_id>")
def triage_status(session_id):
    """Return current triage progress and results (for polling)."""
    triage = get_triage(session_id)
    if not triage:
        return jsonify({"status": "idle"})

    resp = {
        "status": triage["status"],
        "progress": triage["progress"],
    }
    if triage["status"] == "complete":
        resp["results"] = triage["results"]
    if triage["status"] == "failed":
        resp["error"] = triage.get("error", "Unknown error")
    return jsonify(resp)


@triage_bp.route("/triage/single/<issue_key>", methods=["POST"])
def triage_single(issue_key):
    """Re-triage a single ticket by issue_key."""
    data = request.json or {}
    session_id = data.get("session_id")

    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Find the row matching this issue_key
    target_row = None
    for entry in session["data"].values():
        row = entry["row"]
        if row.get("issue_key", "").strip() == issue_key:
            target_row = row
            break

    if not target_row:
        return jsonify({"error": f"Ticket {issue_key} not found in session"}), 404

    team_members = load_team_members()
    try:
        result = categorise_ticket(target_row, team_members)
        result["triage_status"] = "complete"
    except Exception as exc:
        result = {
            "category": "Triage Failed",
            "issue_key": issue_key,
            "assignee": target_row.get("assignee", ""),
            "status": target_row.get("status", ""),
            "updated": target_row.get("updated", ""),
            "last_comment_by": target_row.get("last_comment_by", ""),
            "output": str(exc),
            "triage_status": "failed",
        }

    update_single_triage_result(session_id, issue_key, result)
    return jsonify({"result": result})
