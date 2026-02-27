# JIRA_ANA_AR — MSDW Invoice Automation Platform

## Project Overview

Internal Flask web application for the Medical System Data Warehouse (MSDW) team. Processes JIRA ticket exports (CSV), generates PDF invoices, and sends them via email. Supports both a web UI and a CLI entry point.

## Tech Stack

- **Backend**: Python 3.11+, Flask
- **Frontend**: Single-page HTML, vanilla JS, Tailwind CSS (CDN)
- **PDF**: reportlab (or fpdf2, check requirements.txt)
- **Data**: pandas, numpy
- **Email**: smtplib (standard library)
- **No database** — all session data is in-memory

## Architecture

Layered single-process monolith. Service-driven. Web and CLI share the same core logic.

```
app.py  →  routes/  →  services/  →  utils/config
                         ↑
scripts/generate_invoices.py (CLI)
```

### Dependency Flow (strict, no reverse)

```
app.py → routes → services → utils / config
scripts/ → services → utils / config
```

No circular imports. Routes never import from routes. Services never import from routes.

### File Responsibilities

| File | Does | Does NOT |
|---|---|---|
| `app.py` | Create Flask app, load config, register blueprints | Business logic, route handlers, HTML |
| `config.py` | Environment variables, SMTP settings, defaults | Import Flask or any service |
| `routes/invoice_routes.py` | HTTP endpoints, input validation, call services, return JSON/files | pandas, PDF generation, SMTP calls |
| `services/csv_service.py` | CSV reading, format detection, cleaning, column renaming | Flask, HTTP, file serving |
| `services/invoice_service.py` | PDF generation from row data | Flask, email, CSV parsing |
| `services/email_service.py` | SMTP connection, build & send email with attachment | Flask, CSV, PDF generation |
| `utils/session_store.py` | In-memory storage for session data, PDF paths, send status | Flask request handling, business logic |
| `templates/index.html` | UI layout, references static assets | Inline `<script>` or `<style>` blocks |
| `static/app.js` | All frontend logic: upload, API calls, DOM updates | — |
| `static/style.css` | Custom styles, Tailwind overrides | — |
| `scripts/generate_invoices.py` | CLI argparse wrapper, imports services | Flask, web-specific logic |

## Critical Conventions

### Column Names — DO NOT CHANGE

The following column names contain intentional legacy spellings. They are used across CSV processing, invoice generation, and the frontend. **Never rename them:**

- `sesolution` (not "resolution")
- `costes_or_datarequest` (not "cost_or_data_request")
- `creater` (not "creator")
- `creater_id` (not "creator_id")

### Computed Columns

- `description` — merged from Description + data_request_purpose + Project description
- `last_comment` — last non-empty comment from JIRA comment columns
- `last_comment_by` — author extracted from last_comment (second semicolon-delimited field)
- `send_invoice` — `"yes"` if quote > 0, otherwise `"no"`

### CSV Auto-Detection

`csv_service.py` must auto-detect whether an uploaded CSV is:
1. **Raw JIRA export** — contains columns starting with `"Custom field ("` → run full preprocessing
2. **Already cleaned** — contains `issue_key`, `pi_name`, etc. → skip preprocessing

### PDF Generation

- One PDF per invoice row
- PDFs stored in a temp directory scoped to the current session
- File paths tracked in `session_store`

### Email

- SMTP config comes from `config.py` (environment variables)
- Each email attaches one PDF invoice
- Frontend controls: from, to, cc, subject, body
- `send_invoice == "yes"` determines whether the send button is active for a row

## Project Structure

```
JIRA_ANA_AR/
├── app.py
├── config.py
├── routes/
│   ├── __init__.py
│   └── invoice_routes.py
├── services/
│   ├── __init__.py
│   ├── csv_service.py
│   ├── invoice_service.py
│   └── email_service.py
├── models/
│   └── __init__.py              # empty, reserved for future ORM
├── utils/
│   └── session_store.py
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
├── scripts/
│   └── generate_invoices.py
├── requirements.txt
└── claude.md                    # this file
```

## Common Tasks

### Run the web app
```bash
cd JIRA_ANA_AR
python app.py
```

### Run CLI invoice generation
```bash
python scripts/generate_invoices.py input.csv -o output_dir/
```

### Add a new route
1. Add endpoint in `routes/invoice_routes.py`
2. Create or call service function in `services/`
3. Never put business logic in the route — delegate to service

### Add a new service
1. Create function in appropriate `services/*.py`
2. Import from `config.py` for settings, `utils/` for helpers
3. Never import Flask or routes

## Rules for AI Assistants

1. **Read this file first** before making any changes
2. **Never modify column name spellings** listed above
3. **Respect layer boundaries** — routes call services, services don't call routes
4. **No inline JS/CSS** in HTML — use static/app.js and static/style.css
5. **No business logic in app.py or routes** — delegate to services
6. **Preserve CLI compatibility** — scripts/generate_invoices.py must work without Flask
7. **Test after changes** — verify imports, Flask startup, and at minimum one upload→preview flow
8. **No external database** — use session_store.py for all state
9. **Keep the original project untouched** — it lives in the parent directory as reference
