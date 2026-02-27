"""
triage_service.py
Ticket classification and AI-powered triage.
Pure functions — no Flask dependencies.

Adapted from jira_ticket_processor.py (JIRA_ANA project).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

import requests

from config import (
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    JIRA_BASE_URL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_PREDICT,
    TEAM_MEMBERS,
    TEAM_MEMBERS_FILE,
    TRIAGE_NEW_TICKET_DAYS,
    TRIAGE_RESPONSE_TEMPLATES,
    TRIAGE_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Team members
# ---------------------------------------------------------------------------

def load_team_members() -> set[str]:
    """Load team member IDs from config (env var and/or file)."""
    members: set[str] = set()

    # From comma-separated env var
    if TEAM_MEMBERS:
        for name in TEAM_MEMBERS.split(","):
            name = name.strip().lower()
            if name:
                members.add(name)

    # From file
    if TEAM_MEMBERS_FILE:
        try:
            with open(TEAM_MEMBERS_FILE) as f:
                for line in f:
                    name = line.strip().lower()
                    if name:
                        members.add(name)
        except FileNotFoundError:
            logger.warning("Team members file not found: %s", TEAM_MEMBERS_FILE)

    return members


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def check_llm_available() -> bool:
    """Return True if the configured LLM provider is reachable."""
    provider = LLM_PROVIDER.lower()
    if provider == "ollama":
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False
    elif provider == "claude":
        return bool(CLAUDE_API_KEY)
    return False


def call_llm(prompt: str) -> str:
    """Send a prompt to the configured LLM and return the response text."""
    provider = LLM_PROVIDER.lower()
    if provider == "ollama":
        return _call_ollama(prompt)
    elif provider == "claude":
        return _call_claude(prompt)
    return f"[Unknown LLM provider: {provider}]"


def _call_ollama(prompt: str) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": OLLAMA_NUM_PREDICT},
            },
            timeout=TRIAGE_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.ConnectionError:
        logger.error("Cannot connect to Ollama at %s", OLLAMA_BASE_URL)
        return "[AI summary unavailable - Ollama not running]"
    except requests.Timeout:
        logger.error("Ollama request timed out")
        return "[AI summary unavailable - request timed out]"
    except Exception as exc:
        logger.error("Ollama API call failed: %s", exc)
        return f"[AI summary unavailable - error: {exc}]"


def _call_claude(prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        return "[Claude API unavailable - anthropic package not installed]"

    if not CLAUDE_API_KEY:
        return "[Claude API unavailable - CLAUDE_API_KEY not set]"

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=OLLAMA_NUM_PREDICT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.error("Claude API call failed: %s", exc)
        return f"[AI summary unavailable - error: {exc}]"


# ---------------------------------------------------------------------------
# Row field helpers
# ---------------------------------------------------------------------------

def _get(row: dict, field: str, default: str = "") -> str:
    """Safely get a string field from a row dict."""
    val = row.get(field)
    if val is None:
        return default
    s = str(val).strip()
    return s if s and s.lower() != "nan" else default


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%b/%y %I:%M %p",
]


def _parse_date(value: str | None) -> datetime | None:
    """Try multiple date formats; return naive datetime or None."""
    if not value or value.lower() == "nan":
        return None
    value = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _days_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    delta = datetime.now() - dt
    return delta.total_seconds() / 86400


# ---------------------------------------------------------------------------
# Ticket field checks
# ---------------------------------------------------------------------------

def _is_ask_a_question(row: dict) -> bool:
    return _get(row, "request_type").lower() == "ask a question"


def _is_db_access_request(row: dict) -> bool:
    return (
        _get(row, "request_type").lower()
        == "msdw de-identified database access request"
    )


def _is_continuation(row: dict) -> bool:
    """Check if summary or description references another ticket ID."""
    text = _get(row, "summary") + " " + _get(row, "description")
    return bool(re.search(r"[A-Z]+-\d+", text))


def _has_inclusion(row: dict) -> bool:
    return bool(_get(row, "inclusion"))


def _has_report_fields(row: dict) -> bool:
    return bool(_get(row, "report_fields"))


def _needs_phi(row: dict) -> bool:
    phi = _get(row, "phi").lower()
    return phi in ("yes", "true", "1")


def _has_irb(row: dict) -> bool:
    return bool(_get(row, "irb_num"))


# ---------------------------------------------------------------------------
# Category processors
# ---------------------------------------------------------------------------

def _process_priority1(row: dict, dry_run: bool) -> dict:
    """External user comment - summarise the last comment."""
    issue_key = _get(row, "issue_key", "UNKNOWN")
    last_comment = _get(row, "last_comment")

    if dry_run:
        ai_summary = "[DRY RUN - AI processing skipped]"
    else:
        prompt = (
            "Summarise this JIRA comment in 1-2 short sentences. "
            "State what the user needs and any deadline. No preamble.\n\n"
            f"Ticket: {issue_key}\n"
            f"Comment: {last_comment}"
        )
        ai_summary = call_llm(prompt)

    return {
        "category": "Priority 1: External User Comment",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": _get(row, "updated"),
        "last_comment_by": _get(row, "last_comment_by"),
        "output": f"**USER REQUEST**: {ai_summary}",
    }


def _process_priority2(row: dict) -> dict:
    """Stale ticket - flag for review."""
    issue_key = _get(row, "issue_key", "UNKNOWN")
    updated = _get(row, "updated")
    age = _days_since(_parse_date(updated))
    age_str = f"{int(age)} days" if age else "unknown"
    return {
        "category": "Priority 2: Stale Ticket",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": updated,
        "last_comment_by": _get(row, "last_comment_by"),
        "output": (
            f"**ACTION NEEDED**: This ticket has not been updated in {age_str}. "
            "Please review the ticket for updates."
        ),
    }


def _process_priority3a(row: dict, dry_run: bool) -> dict:
    """Ask a Question ticket - summarise and propose a response."""
    issue_key = _get(row, "issue_key", "UNKNOWN")
    summary = _get(row, "summary")
    description = _get(row, "description")
    last_comment = _get(row, "last_comment")

    if dry_run:
        ai_text = "[DRY RUN - AI processing skipped]"
    else:
        prompt = (
            "A user submitted a JIRA question. Do two things:\n"
            "1. Summarise the question in one sentence.\n"
            "2. Propose a brief response (2-3 sentences max).\n"
            "No preamble. Use this format:\n"
            "QUESTION SUMMARY: ...\nPROPOSED RESPONSE: ...\n\n"
            f"Ticket: {issue_key}\n"
            f"Summary: {summary}\n"
            f"Description: {description}\n"
            f"Latest comment: {last_comment}"
        )
        ai_text = call_llm(prompt)

    return {
        "category": "Priority 3a: Ask a Question",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": _get(row, "updated"),
        "last_comment_by": _get(row, "last_comment_by"),
        "output": ai_text,
    }


def _process_priority3b(row: dict) -> dict:
    """Database access request ticket - flag for review."""
    issue_key = _get(row, "issue_key", "UNKNOWN")
    return {
        "category": "Priority 3b: Database Access Request",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": _get(row, "updated"),
        "last_comment_by": _get(row, "last_comment_by"),
        "output": "**ACTION NEEDED**: This ticket is a Direct database access ticket.",
    }


def _process_priority3c(row: dict, dry_run: bool) -> dict:
    """Continuation ticket - summarise with context."""
    issue_key = _get(row, "issue_key", "UNKNOWN")
    summary = _get(row, "summary")
    description = _get(row, "description")

    refs = re.findall(r"[A-Z]+-\d+", summary + " " + description)
    ref_str = ", ".join(set(refs)) if refs else "unknown"

    if dry_run:
        ai_text = "[DRY RUN - AI processing skipped]"
    else:
        prompt = (
            "This JIRA ticket continues previous work "
            f"(related: {ref_str}). Summarise what the user needs "
            "in 1-2 short sentences. No preamble.\n\n"
            f"Ticket: {issue_key}\n"
            f"Summary: {summary}\n"
            f"Description: {description}"
        )
        ai_text = call_llm(prompt)

    return {
        "category": "Priority 3c: Continuation",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": _get(row, "updated"),
        "last_comment_by": _get(row, "last_comment_by"),
        "output": f"**Related tickets**: {ref_str}\n\n{ai_text}",
    }


def _process_priority3d(row: dict) -> dict:
    """New request ticket - check required info and generate email."""
    issue_key = _get(row, "issue_key", "UNKNOWN")
    reporter = _get(row, "reporter") or _get(row, "creater") or "Requestor"

    has_inclusion = _has_inclusion(row)
    has_fields = _has_report_fields(row)
    needs_phi = _needs_phi(row)
    has_irb = _has_irb(row)

    templates = TRIAGE_RESPONSE_TEMPLATES
    missing_parts: list[str] = []

    if not has_inclusion:
        missing_parts.append(templates.get(
            "missing_cohort",
            "- Cohort criteria (inclusion/exclusion criteria for your study)",
        ))
    if not has_fields:
        missing_parts.append(templates.get(
            "missing_report_fields",
            "- Report fields (the data elements you need in your dataset)",
        ))
    if needs_phi and not has_irb:
        missing_parts.append(templates.get(
            "missing_irb",
            "- IRB approval number (required for PHI access)",
        ))

    missing_items = "\n".join(missing_parts)
    email_template = templates.get(
        "availability_request",
        "Dear [User],\n\nThank you for submitting your request. "
        "We'd like to schedule a time to discuss your needs.\n\n"
        "Could you please provide:\n- Your availability for a brief call this week\n"
        "{missing_items}\n\nBest regards,\nThe Team",
    )
    email = email_template.replace("[User]", reporter).replace("{missing_items}", missing_items)

    checks: list[str] = []
    checks.append(f"Inclusion criteria provided: {'Yes' if has_inclusion else '**No - MISSING**'}")
    checks.append(f"Report fields provided: {'Yes' if has_fields else '**No - MISSING**'}")
    checks.append(f"PHI required: {'Yes' if needs_phi else 'No'}")
    if needs_phi:
        checks.append(f"IRB number provided: {'Yes' if has_irb else '**No - MISSING**'}")

    output = "**Information Check**:\n" + "\n".join(f"- {c}" for c in checks)
    output += "\n\n**Proposed Email**:\n```\n" + email + "\n```"

    return {
        "category": "Priority 3d: New Request",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": _get(row, "updated"),
        "last_comment_by": _get(row, "last_comment_by"),
        "output": output,
    }


# ---------------------------------------------------------------------------
# Main classification engine
# ---------------------------------------------------------------------------

def categorise_ticket(
    row: dict,
    team_members: set[str],
    new_ticket_days: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Assign a ticket to exactly one priority category and process it.

    Returns a result dict with keys: category, issue_key, status, updated,
    last_comment_by, output.  Never returns None — uncategorised tickets get
    "No Action Required".
    """
    if new_ticket_days is None:
        new_ticket_days = TRIAGE_NEW_TICKET_DAYS

    issue_key = _get(row, "issue_key")
    if not issue_key:
        return {
            "category": "Triage Failed",
            "issue_key": "UNKNOWN",
            "assignee": _get(row, "assignee"),
            "status": "",
            "updated": "",
            "last_comment_by": "",
            "output": "Missing issue_key — cannot triage.",
        }

    commenter = _get(row, "last_comment_by").lower()
    updated_dt = _parse_date(_get(row, "updated"))
    created_dt = _parse_date(_get(row, "created"))
    age_days = _days_since(updated_dt)
    status = _get(row, "status").lower()

    # Priority 1: External user comment
    if commenter and commenter not in team_members:
        logger.info("%s -> Priority 1 (external comment by %s)", issue_key, commenter)
        return _process_priority1(row, dry_run)

    # Priority 2: Stale ticket (last comment by team member, >7 days ago)
    if commenter in team_members and age_days is not None and age_days > 7:
        logger.info("%s -> Priority 2 (stale, %.0f days)", issue_key, age_days)
        return _process_priority2(row)

    # Priority 3: Newly created tickets with status "To Do"
    created_age = _days_since(created_dt)
    if (
        created_age is not None
        and created_age <= new_ticket_days
        and status == "to do"
    ):
        if _is_ask_a_question(row):
            logger.info("%s -> Priority 3a (ask a question)", issue_key)
            return _process_priority3a(row, dry_run)

        if _is_db_access_request(row):
            logger.info("%s -> Priority 3b (database access request)", issue_key)
            return _process_priority3b(row)

        if _is_continuation(row):
            logger.info("%s -> Priority 3c (continuation)", issue_key)
            return _process_priority3c(row, dry_run)

        logger.info("%s -> Priority 3d (new request)", issue_key)
        return _process_priority3d(row)

    reporter = _get(row, "reporter") or _get(row, "creater")
    logger.info("%s -> No action required (reporter: %s)", issue_key, reporter)
    return {
        "category": "No Action Required",
        "issue_key": issue_key,
        "assignee": _get(row, "assignee"),
        "status": _get(row, "status"),
        "updated": _get(row, "updated"),
        "last_comment_by": _get(row, "last_comment_by"),
        "output": "",
    }


# ---------------------------------------------------------------------------
# Batch triage (main entry point for the web layer)
# ---------------------------------------------------------------------------

def triage_tickets(
    rows: list[dict],
    progress_callback=None,
    dry_run: bool = False,
) -> list[dict]:
    """Triage all rows and return a list of result dicts.

    Parameters
    ----------
    rows : list[dict]
        Row dicts (output of csv_service / session_store).
    progress_callback : callable, optional
        Called as ``progress_callback(completed, total, current_issue_key)``
        after each ticket is processed.
    dry_run : bool
        If True, skip actual LLM calls.
    """
    team_members = load_team_members()
    llm_ok = check_llm_available()
    effective_dry_run = dry_run or not llm_ok

    if not llm_ok:
        logger.warning(
            "LLM (%s) is not available — running in dry-run mode", LLM_PROVIDER,
        )

    results: list[dict] = []
    total = len(rows)

    for i, row in enumerate(rows):
        issue_key = _get(row, "issue_key", f"row-{i}")
        try:
            result = categorise_ticket(
                row, team_members, dry_run=effective_dry_run,
            )
            result["triage_status"] = "complete"
        except Exception as exc:
            logger.error("Triage failed for %s: %s", issue_key, exc)
            result = {
                "category": "Triage Failed",
                "issue_key": issue_key,
                "assignee": _get(row, "assignee"),
                "status": _get(row, "status"),
                "updated": _get(row, "updated"),
                "last_comment_by": _get(row, "last_comment_by"),
                "output": str(exc),
                "triage_status": "failed",
            }

        results.append(result)

        if progress_callback:
            progress_callback(i + 1, total, issue_key)

    return results
