1) make it a git project
2) add a hook, such that it performs a git commit after every feature update. 
3) add prehook or permission idk how it works in claude such that dangerous comments are not allowed or require developer approval.
4) also, no need to ask for permission for read bash commands since reading files is save
5) when i do the manual application, it doesnt currently go inside the applied bucket, maybe since you might not be able to detect it whether i applied or not, you can ask me if i have applied in the manual scenario and based on my response add it to there.
6) i dont have anthropic api key, however, i have pro subscription so can't the app use that to generate cover letter by especially checking my github repos and finding relevant projects to help with cover letter. 
7) save the session data somewhere, especially the list of applied or rejected ones and reload the data for a new session


# Job Hunter — Feature Batch Implementation Plan

## Context

The job hunter app is fully functional (scrapers, keyword scoring, review queue UI, Gmail/Playwright senders). The user has 6 feature requests from `to_implement.txt` covering project setup, Claude Code configuration, a UI bug fix, and AI-powered cover letter generation.

---

## Feature 1: Initialize Git Repository

**Files:** `.gitignore` (new)

Create `.gitignore` then `git init` and initial commit.

```
__pycache__/
*.pyc
.venv/
data/db.sqlite
data/gmail_token.json
data/gmail_credentials.json
.env
*.egg-info/
.pytest_cache/
```

Run: `git init && git add . && git commit -m "Initial commit: job hunter application"`

---

## Feature 2: Auto-Commit Hook After File Changes

**Files:** `.claude/settings.json` (new, project-level)

Claude Code hooks use this schema (verified from CLI source v2.1.104):
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "cd /home/hevra/Desktop/projects/after_masters/job_hunter && git add -A && git diff --cached --quiet || git commit -m 'Auto-commit: files updated by Claude Code'"
          }
        ]
      }
    ]
  }
}
```

Key details from source:
- Hook events: `PreToolUse`, `PostToolUse`, etc.
- Each event maps to an array of `{matcher, hooks}` objects
- `matcher` is a string pattern matched against tool names (e.g. `"Write|Edit"`)
- Each hook has `type: "command"` and a `command` string
- Hook receives JSON via stdin with `tool_name`, `tool_input`, etc.

---

## Feature 3: Pre-Hook to Block Dangerous Commands

**Files:** `.claude/settings.json` (same file as Feature 2), `.claude/check_dangerous.sh` (new)

Add a `PreToolUse` hook that checks Bash commands against dangerous patterns. The hook command receives JSON on stdin containing `{"tool_name": "Bash", "tool_input": {"command": "..."}}`.

**`.claude/check_dangerous.sh`:**
```bash
#!/bin/bash
# Reads hook JSON from stdin, checks if the bash command is dangerous.
# Exit 0 = allow, exit 2 = block (shows error to model).
INPUT=$(cat)
TOOL=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

DANGEROUS='rm -rf|git push.*--force|git reset --hard|DROP TABLE|DELETE FROM|chmod -R 777|mkfs|dd if=|> /dev/'
if echo "$TOOL" | grep -qiE "$DANGEROUS"; then
  echo "BLOCKED: dangerous command detected: $TOOL"
  exit 2
fi
exit 0
```

Hook config (added to PreToolUse in settings.json):
```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "bash .claude/check_dangerous.sh"
      }
    ]
  }
]
```

---

## Feature 4: Auto-Allow Read-Only Bash Commands

**Files:** `.claude/settings.json` (same file)

Add `permissions.allow` list. Claude Code uses glob patterns like `Bash(git status*)`:

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Glob",
      "Grep",
      "Bash(ls *)",
      "Bash(cat *)",
      "Bash(head *)",
      "Bash(tail *)",
      "Bash(find *)",
      "Bash(git status*)",
      "Bash(git log*)",
      "Bash(git diff*)",
      "Bash(git show*)",
      "Bash(git branch*)",
      "Bash(wc *)",
      "Bash(file *)",
      "Bash(pwd)",
      "Bash(which *)",
      "Bash(echo *)"
    ]
  }
}
```

---

## Feature 5: Manual Application "Mark as Applied"

**Files:** `main.py` (add endpoint ~line 289), `ui/templates/job_detail.html` (lines 215-220 + scripts)

**Problem:** When a job is marked manual, `job.status` stays `"approved"` forever. No way to confirm manual submission.

### Backend — `main.py`

Add after the `send_application` endpoint (~line 289):

```python
@app.post("/api/jobs/{job_id}/mark-applied")
def mark_applied(job_id: int, session: Session = Depends(get_session)):
    """Mark a manually-applied job as applied."""
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "approved":
        raise HTTPException(status_code=400, detail="Job must be in approved status")
    application = get_application(session, job_id)
    if not application:
        raise HTTPException(status_code=400, detail="No application found")

    job.status = "applied"
    application.send_status = "sent"
    application.sent_at = datetime.utcnow()
    session.add(job)
    session.add(application)
    session.commit()
    return {"status": "applied", "job_id": job_id}
```

Also update the docstring at line 11 to include `POST /api/jobs/{id}/mark-applied`.

### Frontend — `job_detail.html`

In the manual-badge block (lines 215-220), add a "Mark as Applied" button after the "Open job page" link:

```html
<button class="btn btn-success btn-sm" style="margin-top:0.5rem; display:inline-flex;"
        onclick="markAsApplied()">Mark as Applied</button>
```

Add JS function in the `<script>` block:

```javascript
async function markAsApplied() {
  if (!confirm('Confirm that you have manually applied for this job?')) return;
  try {
    await apiPost(`/api/jobs/${JOB_ID}/mark-applied`);
    flash('Marked as applied!', 'success');
    setTimeout(() => location.reload(), 1200);
  } catch(e) {
    flash(e.message, 'error');
  }
}
```

---

## Feature 6: Claude CLI Cover Letter Generation

**Files:** `ai/cover_letter.py` (rewrite), `main.py` (add regenerate endpoint), `ui/templates/job_detail.html` (add Regenerate button), `config.yaml` (add `github_username` + `use_ai_cover_letter`)

### How it works

The Claude Code CLI at `/home/hevra/.npm-global/bin/claude` supports `-p` (print mode, non-interactive). It uses the user's Pro subscription — no API key needed. We call it via `subprocess.run()`.

### `ai/cover_letter.py` — Full rewrite

```python
"""Cover letter generation: Claude CLI with template fallback."""
import logging
import subprocess
from pathlib import Path

import httpx
import yaml
from pypdf import PdfReader

logger = logging.getLogger(__name__)

CLAUDE_CLI = "/home/hevra/.npm-global/bin/claude"


def generate_cover_letter(title, organization, description, job_type, **kwargs):
    """Try Claude CLI first, fall back to template."""
    cfg = _load_config()
    if cfg.get("use_ai_cover_letter", True):
        try:
            return _generate_with_claude(title, organization, description, job_type, cfg)
        except Exception as e:
            logger.warning("Claude CLI cover letter failed: %s. Using template.", e)
    return _generate_template(title, organization, description, job_type)


def _generate_with_claude(title, organization, description, job_type, cfg):
    """Call Claude CLI in print mode to generate a personalized cover letter."""
    user = cfg.get("user", {})
    cv_text = _read_cv(cfg.get("attachments", {}).get("cv", "assets/cv.pdf"))
    github_summary = _fetch_github_repos(cfg.get("github_username", "hevra01"))

    prompt = f"""Write a cover letter for this position:

POSITION: {title} at {organization}
POSITION TYPE: {job_type}

JOB DESCRIPTION:
{description[:3000]}

MY BACKGROUND (from CV):
{cv_text[:2000]}

MY GITHUB PROJECTS:
{github_summary}

MY CONTACT INFO:
Name: {user.get('name', '')}
Email: {user.get('email', '')}
Phone: {user.get('phone', '')}
GitHub: https://github.com/{cfg.get('github_username', 'hevra01')}

INSTRUCTIONS:
- Write a ready-to-send cover letter (no placeholder brackets)
- Keep it under 400 words
- Reference specific GitHub projects relevant to this role
- For PhD/postdoc: emphasize research interests and academic background
- For ML engineer: emphasize practical skills and project outcomes
- Professional but not overly formal
- Include proper greeting and sign-off with contact info
"""

    result = subprocess.run(
        [CLAUDE_CLI, "-p", "--model", "sonnet", "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI exit {result.returncode}: {result.stderr[:200]}")

    text = result.stdout.strip()
    if not text:
        raise RuntimeError("Claude CLI returned empty output")
    return text


def _generate_template(title, organization, description, job_type):
    """Fallback: static template for the user to fill in."""
    greeting = "Dear Hiring Committee," if job_type == "ml_engineer" else "Dear Professor / Hiring Committee,"
    closing = "\nA recommendation letter is available upon request." if job_type in ("phd", "postdoc") else ""

    return (
        f"{greeting}\n\n"
        f"I am writing to apply for the {title} position at {organization}.\n\n"
        f"[Introduce yourself and your background]\n\n"
        f"[Explain why this specific role/lab interests you]\n\n"
        f"[Describe your most relevant experience]\n"
        f"{closing}\n\n"
        f"Sincerely,\nHevra Petekkaya\n"
        f"hevrapetekkaya01@gmail.com | +49 17632086462\n"
        f"https://github.com/hevra01"
    )


def _read_cv(cv_path="assets/cv.pdf"):
    """Extract text from CV PDF."""
    path = Path(cv_path)
    if not path.exists():
        return "CV file not found."
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)[:2000]


def _fetch_github_repos(username="hevra01"):
    """Fetch public repos from GitHub API."""
    try:
        resp = httpx.get(
            f"https://api.github.com/users/{username}/repos",
            params={"sort": "updated", "per_page": 10},
            timeout=10,
        )
        repos = resp.json()
        lines = []
        for r in repos:
            if r.get("fork"):
                continue
            lines.append(f"- {r['name']} ({r.get('language', '?')}): {r.get('description', 'No description')}")
        return "\n".join(lines) if lines else "No public repos found."
    except Exception:
        return "GitHub repos unavailable."


def _load_config(config_path="config.yaml"):
    with open(config_path) as f:
        return yaml.safe_load(f)
```

### `main.py` — Add regenerate endpoint

Add after the `mark-applied` endpoint:

```python
@app.post("/api/jobs/{job_id}/cover-letter")
def regenerate_cover_letter(job_id: int, session: Session = Depends(get_session)):
    """Regenerate cover letter using Claude CLI."""
    from ai.cover_letter import generate_cover_letter

    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    application = get_application(session, job_id)
    if not application:
        raise HTTPException(status_code=400, detail="No application found")

    cover_letter = generate_cover_letter(
        title=job.title,
        organization=job.organization,
        description=job.description,
        job_type=job.job_type,
    )
    application.cover_letter = cover_letter
    application.edited_cover_letter = None  # clear edits so new text shows
    session.add(application)
    session.commit()
    return {"cover_letter": cover_letter}
```

### `job_detail.html` — Add "Regenerate with AI" button

After the textarea (line 230), add:

```html
<button class="btn btn-outline btn-sm" onclick="regenerateCoverLetter()" style="margin-top:0.5rem;">
  Regenerate with AI
</button>
```

JS function:
```javascript
async function regenerateCoverLetter() {
  if (!confirm('Regenerate cover letter using AI? This replaces the current text.')) return;
  flash('Generating cover letter with AI... (may take 30-60s)', 'info');
  try {
    const result = await apiPost(`/api/jobs/${JOB_ID}/cover-letter`);
    document.getElementById('cover-letter').value = result.cover_letter;
    flash('Cover letter generated!', 'success');
  } catch(e) {
    flash(e.message, 'error');
  }
}
```

### `config.yaml` — Add new fields

```yaml
user:
  name: "Hevra Petekkaya"
  # ... existing fields ...

github_username: "hevra01"
use_ai_cover_letter: true  # false = always use template, true = try Claude CLI
```

### Scheduler note

No changes to `scheduler.py`. It already calls `generate_cover_letter()` — the new version will try Claude CLI automatically during discovery. If CLI is slow or fails, it falls back to the template. The 120s timeout per call is safe since discovery runs in a background thread.

---

## Implementation Order

1. **Feature 1** — git init (so all later changes are tracked)
2. **Features 2+3+4** — `.claude/settings.json` + `check_dangerous.sh` (one commit)
3. **Feature 5** — mark-applied endpoint + UI button (one commit)
4. **Feature 6** — Claude CLI cover letters (one commit)

## Verification

1. `git log` — shows initial commit + subsequent feature commits
2. Make a small edit via Claude Code → verify auto-commit hook fires
3. Try a `rm -rf` via Claude Code → verify it's blocked by pre-hook
4. Run `ls` via Claude Code → verify no permission prompt (auto-allowed)
5. Approve a job with "Mark as manual" → send → click "Mark as Applied" → verify it moves to "applied" tab
6. Run `claude auth status` to confirm CLI is authenticated
7. Navigate to a queued job → click "Regenerate with AI" → verify personalized cover letter appears
8. Start server, trigger scrape → verify new jobs get AI-generated cover letters (or template fallback)
