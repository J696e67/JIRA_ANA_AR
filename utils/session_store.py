"""
session_store.py
In-memory session storage: uploaded data, PDF paths, invoice state.
"""

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
