"""
session_store.py
In-memory session storage: uploaded data, PDF paths, invoice state, triage state.
"""

# ── Invoice sessions ───────────────────────────────────────────────────
# { session_id: { "output_dir": str, "data": { invoice_id: entry } } }
_sessions = {}


def store_session(session_id, data):
    """Store session data keyed by session_id."""
    _sessions[session_id] = data


def get_session(session_id):
    """Return session data for the given session_id, or None."""
    return _sessions.get(session_id)


def clear_session(session_id):
    """Remove a session from the store."""
    _sessions.pop(session_id, None)


# ── Triage state ──────────────────────────────────────────────────────
# { session_id: { "status": str, "progress": dict, "results": list, "error": str|None } }
_triage = {}


def init_triage(session_id, total):
    """Initialise triage state for a session."""
    _triage[session_id] = {
        "status": "processing",
        "progress": {"total": total, "completed": 0, "current": None},
        "results": [],
        "error": None,
    }


def get_triage(session_id):
    """Return triage state for the given session_id, or None."""
    return _triage.get(session_id)


def update_triage_progress(session_id, completed, current_key=None):
    """Update triage progress counters."""
    entry = _triage.get(session_id)
    if entry:
        entry["progress"]["completed"] = completed
        entry["progress"]["current"] = current_key


def store_triage_results(session_id, results):
    """Mark triage as complete and store all results."""
    entry = _triage.get(session_id)
    if entry:
        entry["status"] = "complete"
        entry["results"] = results
        entry["progress"]["current"] = None


def set_triage_failed(session_id, error_msg):
    """Mark triage as failed."""
    entry = _triage.get(session_id)
    if entry:
        entry["status"] = "failed"
        entry["error"] = error_msg


def update_single_triage_result(session_id, issue_key, result):
    """Replace or append a single ticket's triage result."""
    entry = _triage.get(session_id)
    if not entry:
        return
    results = entry.get("results", [])
    for i, r in enumerate(results):
        if r.get("issue_key") == issue_key:
            results[i] = result
            return
    results.append(result)
