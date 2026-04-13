"""
Cover letter generation: Claude CLI with template fallback.

Uses the Claude Code CLI (`claude -p`) with the user's Pro subscription
to generate personalized cover letters from CV + GitHub repos + job description.
Falls back to a static template if the CLI is unavailable.
"""
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
    github_username = cfg.get("github_username", "hevra01")
    github_summary = _fetch_github_repos(github_username)

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
GitHub: https://github.com/{github_username}

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
    closing = (
        "\nA recommendation letter is available upon request."
        if job_type in ("phd", "postdoc")
        else ""
    )

    return (
        f"{greeting}\n\n"
        f"I am writing to apply for the {title} position at {organization}.\n\n"
        f"[Introduce yourself and your background]\n\n"
        f"[Explain why this specific role/lab interests you]\n\n"
        f"[Describe your most relevant experience]\n"
        f"{closing}\n\n"
        f"I would welcome the opportunity to discuss how my background aligns with your needs.\n\n"
        f"Sincerely,\n"
        f"Hevra Petekkaya\n"
        f"hevrapetekkaya01@gmail.com | +49 17632086462\n"
        f"https://github.com/hevra01"
    )


def _read_cv(cv_path="assets/cv.pdf"):
    """Extract text from CV PDF using pypdf."""
    path = Path(cv_path)
    if not path.exists():
        return "CV file not found."
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)[:2000]


def _fetch_github_repos(username="hevra01"):
    """Fetch public repos from GitHub API and format a summary."""
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
    """Load config from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)
