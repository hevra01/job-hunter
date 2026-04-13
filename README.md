# Job Hunter

Automated job hunting pipeline for academic and ML research positions. Scrapes job boards and lab websites, scores postings by keyword relevance, generates personalized cover letters (via Claude CLI or template), and sends applications via Gmail API or Playwright form-filling. A web UI lets you review, edit, approve, and send each application.

## Features

- **Multi-source scraping** — Euraxess, AcademicPositions, jobs.ac.uk, individual lab career pages, company portals (Greenhouse/Lever/generic), LinkedIn (optional)
- **Keyword scoring** — Tiered 0–100 relevance scoring based on domain keywords, job type, location, and exclusion filters
- **AI cover letters** — Generates personalized cover letters using Claude CLI with your CV + GitHub repos as context; falls back to an editable template
- **Review queue UI** — Web dashboard to browse, approve, reject, and edit applications before sending
- **Email + form sending** — Gmail API for email applications, Playwright for online form submissions
- **Scheduled discovery** — APScheduler runs the full pipeline on a configurable interval

## Prerequisites

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (optional, for AI cover letters — requires a Claude Pro/Max subscription)
- A Gmail account with OAuth credentials (for sending applications via email)
- Chromium (installed via Playwright, for form-filling)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/hevra01/job-hunter.git
cd job-hunter
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install Playwright browser

```bash
playwright install chromium
```

### 4. Configure your profile

Edit `config.yaml` with your details:

```yaml
user:
  name: "Your Name"
  email: "your.email@gmail.com"
  phone: "+1234567890"
  location: "Your City, Country"

github_username: "your-github-username"
use_ai_cover_letter: true   # set to false to always use the template
```

Customize the `targets` section with your preferred position types, keywords, locations, and minimum relevance score. Add or remove entries under `academic_boards`, `labs`, and `companies` to control which sources are scraped.

### 5. Add your documents

Place your files in the `assets/` directory:

- `assets/cv.pdf` — your CV (required)
- `assets/recommendation.pdf` — recommendation letter (optional, attached for PhD/postdoc applications)

### 6. Set up environment variables

Create a `.env` file in the project root:

```
CONFIG_PATH=config.yaml
GMAIL_CREDENTIALS_FILE=data/gmail_credentials.json
GMAIL_TOKEN_FILE=data/gmail_token.json
```

### 7. Gmail OAuth setup (for sending emails)

1. Create a Google Cloud project and enable the Gmail API
2. Download OAuth client credentials as `data/gmail_credentials.json`
3. Run the first-time auth flow:

```bash
python -m sender.gmail --setup
```

This opens a browser for Google OAuth and saves `data/gmail_token.json`.

### 8. Claude CLI setup (for AI cover letters)

If you have a Claude Pro or Max subscription and want AI-generated cover letters:

```bash
# Install Claude Code CLI (if not already installed)
npm install -g @anthropic-ai/claude-code

# Verify authentication
claude auth status
```

If the CLI is not installed or not authenticated, cover letters will fall back to an editable template.

**Note:** Update the `CLAUDE_CLI` path in `ai/cover_letter.py` if your CLI is installed at a different location than the default.

## Running the App

### Start the web server

```bash
uvicorn main:app --reload
```

The dashboard is available at **http://localhost:8000**.

### Run a one-shot discovery pipeline (no server)

```bash
python scheduler.py
```

This scrapes all configured sources, scores the results, generates cover letter drafts, and saves everything to the database.

## Usage

1. **Discovery** — The scheduler scrapes configured sources automatically (default: every 24h). You can also trigger a manual scrape from the API: `POST /api/scrape`.
2. **Review** — Open the dashboard at `http://localhost:8000`. Jobs scoring above `min_relevance_score` appear in the **Queued** tab.
3. **Approve/Reject** — Click into a job to see the full description, relevance reasoning, and cover letter draft. Edit the cover letter, toggle attachments, then click **Approve** or **Reject**.
4. **Send** — Once approved, click **Send Application** to deliver via email or form. If automated sending fails, the job is marked for manual application — click **Mark as Applied** after you apply manually.

## Job Lifecycle

```
new (score < threshold)
  → queued (score >= threshold, shown in dashboard)
    → approved (user approves)
      → applied (sent successfully or marked manually)
    → rejected (user rejects)
```

## Project Structure

```
main.py              FastAPI app, all HTTP endpoints, lifespan scheduler
scheduler.py         Discovery pipeline: scrape → score → cover letter → DB
models.py            SQLModel ORM (Job + Application), SQLite at data/db.sqlite
config.yaml          All user settings and scrape targets

scrapers/
  base.py            RawJob dataclass, BaseScraper ABC, helpers
  academic_boards.py Euraxess, AcademicPositions, jobs.ac.uk
  lab_websites.py    Lab career page scraper
  company_careers.py Greenhouse/Lever/generic company portals
  linkedin.py        LinkedIn scraper (cookie-based, off by default)

ai/
  scorer.py          Keyword-based 0–100 relevance scorer
  cover_letter.py    Claude CLI cover letter generation + template fallback

sender/
  gmail.py           Gmail API OAuth2 email sender
  form_filler.py     Playwright-based form filler (Greenhouse/Lever/Workday/generic)

ui/
  templates/         Jinja2 templates (base, dashboard, job detail)
  static/            CSS + JS
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard (HTML) |
| `GET` | `/job/{id}` | Job detail page (HTML) |
| `GET` | `/api/jobs` | List jobs (JSON) |
| `GET` | `/api/jobs/{id}` | Job detail (JSON) |
| `POST` | `/api/jobs/{id}/approve` | Approve job for sending |
| `POST` | `/api/jobs/{id}/reject` | Reject job |
| `POST` | `/api/jobs/{id}/send` | Send the application |
| `POST` | `/api/jobs/{id}/mark-applied` | Confirm manual application |
| `POST` | `/api/jobs/{id}/cover-letter` | Regenerate cover letter with AI |
| `POST` | `/api/scrape` | Trigger manual discovery run |
| `GET` | `/api/stats` | Pipeline statistics |

## License

MIT
