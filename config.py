"""
config.py
All configuration: SMTP, file paths, hourly rate, defaults.
Values are read from environment variables with sensible defaults.
"""
import os

# SMTP settings
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Default email addresses
DEFAULT_FROM_ADDR = os.environ.get("DEFAULT_FROM_ADDR", "nicejingy@gmail.com")
DEFAULT_TO_ADDR = os.environ.get("DEFAULT_TO_ADDR", "nicejingy@gmail.com")
DEFAULT_CC_ADDR = os.environ.get("DEFAULT_CC_ADDR", "jing.yang@mssm.edu")

# Invoice settings
HOURLY_RATE = float(os.environ.get("HOURLY_RATE", "177"))

# Upload limits
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "16"))

# ── Triage / LLM settings ─────────────────────────────────────────────

# Provider: "ollama" (local) or "claude" (Anthropic API)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")

# Ollama
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "150"))

# Claude API (only used when LLM_PROVIDER == "claude")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250514")

# Triage behaviour
TRIAGE_TIMEOUT = int(os.environ.get("TRIAGE_TIMEOUT", "120"))
TRIAGE_NEW_TICKET_DAYS = int(os.environ.get("TRIAGE_NEW_TICKET_DAYS", "2"))

# Team members: comma-separated user IDs (lowercase), or path to a text file
TEAM_MEMBERS = os.environ.get("TEAM_MEMBERS", "")
TEAM_MEMBERS_FILE = os.environ.get("TEAM_MEMBERS_FILE", "")

# JIRA base URL for ticket links
JIRA_BASE_URL = os.environ.get(
    "JIRA_BASE_URL",
    "https://scicomp.atlassian.net/jira/servicedesk/projects/MSD/queues/custom/34",
)

# Default response templates for Priority 3d (new request) emails
TRIAGE_RESPONSE_TEMPLATES = {
    "missing_cohort": "- Cohort criteria (inclusion/exclusion criteria for your study)",
    "missing_report_fields": "- Report fields (the data elements you need in your dataset)",
    "missing_irb": "- IRB approval number (required for PHI access)",
    "availability_request": (
        "Dear [User],\n\n"
        "Thank you for submitting your request. "
        "We'd like to schedule a time to discuss your needs.\n\n"
        "Could you please provide:\n"
        "- Your availability for a brief call this week\n"
        "{missing_items}\n\n"
        "Best regards,\nThe Team"
    ),
}
