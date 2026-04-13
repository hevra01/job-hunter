# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An automated job hunting pipeline for academic/ML research positions. It scrapes job boards and lab websites, scores postings by keyword relevance, generates cover letter templates, and sends applications via Gmail API or Playwright form-filling. A FastAPI web UI lets the user review, edit, approve, and send each application.

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (needed for form-filling)
playwright install chromium

# Start the web server (runs on http://localhost:8000)
uvicorn main:app --reload

# Run a one-shot discovery pipeline without starting the server
python scheduler.py
```

## Environment / Secrets

Create a `.env` file (not committed) with:
```
CONFIG_PATH=config.yaml          # optional override
GMAIL_CREDENTIALS_FILE=data/gmail_credentials.json
GMAIL_TOKEN_FILE=data/gmail_token.json
```

Gmail OAuth first-time setup:
```bash
python -m sender.gmail --setup
```
This opens a browser auth flow and saves `data/gmail_token.json`.

## Config

`config.yaml` is the single control plane for everything:
- `user` — applicant name/email/phone used in cover letters and emails
- `targets` — position types, domain keywords, locations, `min_relevance_score` threshold
- `scraping_interval` — how often APScheduler re-runs discovery (e.g. `"24h"`)
- `academic_boards`, `labs`, `companies` — which sources are active and their search terms
- `linkedin.enabled` — off by default; requires session cookies at `data/linkedin_cookies.json`
- `attachments.cv` / `attachments.recommendation_letter` — paths to PDF files in `assets/`

## Architecture

```
main.py          FastAPI app; lifespan starts APScheduler; all HTTP endpoints
scheduler.py     run_discovery() pipeline: build scrapers → scrape → score → cover letter → DB
models.py        SQLModel ORM: Job + Application tables; SQLite at data/db.sqlite
config.yaml      All user settings and scrape targets

scrapers/
  base.py              RawJob dataclass, BaseScraper ABC, classify_job_type(), extract_email()
  academic_boards.py   Euraxess, AcademicPositions, jobs.ac.uk scrapers
  lab_websites.py      LabWebsiteScraper — fetches configured lab openings pages
  company_careers.py   build_company_scrapers() — Greenhouse/Lever/generic company portals
  linkedin.py          LinkedInScraper (cookie-based, off by default)

ai/
  scorer.py       Keyword-based 0–100 scorer (no API key): Tier1=domain kws, Tier2=job type,
                  Tier3=location, Tier4=no exclusion kws. Returns score, reasoning, job_type_detected
  cover_letter.py Returns a blank template string for the user to fill in the UI

sender/
  gmail.py        OAuth2 Gmail API send; token stored at data/gmail_token.json
  form_filler.py  Playwright-based form filler; detects Greenhouse/Lever/Workday/generic portals

ui/
  templates/      Jinja2: base.html, dashboard.html, job_detail.html
  static/         CSS + JS for the review queue UI
```

### Job lifecycle (status field)

`new` (score < min_relevance_score) → `queued` (auto, score ≥ threshold) → `approved` (user action) → `applied` (sent) or `rejected` / `archived`

Only jobs with `status=queued` appear in the default dashboard view. An `Application` row is only created for jobs that cross the score threshold.

### Deduplication

Jobs are deduplicated by URL (`Job.url` has a unique constraint). `job_exists()` checks before inserting.

### Adding a new scraper

1. Create a class in `scrapers/` extending `BaseScraper`, implementing `scrape() -> list[RawJob]`
2. Add it to `build_scrapers()` in `scheduler.py`
3. Add any needed config keys to `config.yaml`

### Scoring / cover letter customization

- Edit keyword lists and tier weights directly in `ai/scorer.py`
- Cover letter template is in `ai/cover_letter.py` — it is a plain string template, no AI API calls
- The `POST /api/jobs/{id}/cover-letter` endpoint is wired in `main.py` but not yet fully implemented (placeholder)

## Code Style
- Prefer simple readable code over clever abstractions
- Always add docstrings to new functions
- Keep changes minimal and surgical

## Do Not
- Never auto-send emails without explicit user approval
- Don't modify config.yaml defaults
- Don't add new dependencies without asking first