"""
Import LeetCode interview problems from GitHub dataset.

Data source: github.com/liquidslr/interview-company-wise-problems
Each company folder has CSV files for different recency windows (30d, 90d, 6m, older, all).
CSV columns: Difficulty, Title, Frequency, Acceptance Rate, Link, Topics
"""
import csv
import io
import logging
from typing import Optional

import httpx
import yaml
from sqlmodel import Session

from models import InterviewProblem

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

RECENCY_MAP = {
    "1. Thirty Days.csv": "30d",
    "2. Three Months.csv": "90d",
    "3. Six Months.csv": "6m",
    "4. More Than Six Months.csv": "older",
    "5. All.csv": "all",
}


def import_all_problems(config_path: str = "config.yaml") -> dict:
    """Import problems for all configured companies. Returns {company: count}."""
    cfg = _load_config(config_path)
    prep_cfg = cfg.get("interview_prep", {})
    repo = prep_cfg.get("github_repo", "liquidslr/interview-company-wise-problems")
    companies = prep_cfg.get("companies", [])

    from models import engine
    results = {}
    with Session(engine) as session:
        for company in companies:
            name = company["name"]
            folder = company["folder"]
            try:
                count = import_company_problems(repo, folder, session)
                results[name] = count
                logger.info("Imported %d problems for %s", count, name)
            except Exception as e:
                logger.error("Failed to import %s: %s", name, e)
                results[name] = -1
    return results


def import_company_problems(repo: str, company_folder: str, session: Session) -> int:
    """Fetch all CSVs for one company from GitHub, parse, and insert. Returns count of new rows."""
    # List files in the company folder
    url = f"{GITHUB_API}/repos/{repo}/contents/{company_folder}"
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    files = resp.json()

    total_new = 0
    for file_info in files:
        filename = file_info["name"]
        recency = RECENCY_MAP.get(filename)
        if not recency:
            continue

        download_url = file_info.get("download_url")
        if not download_url:
            continue

        csv_text = _fetch_csv_content(download_url)
        problems = _parse_csv(csv_text, company_folder, recency)

        for p in problems:
            # Skip if already exists
            from models import InterviewProblem as IP
            from sqlmodel import select
            existing = session.exec(
                select(IP).where(
                    IP.leetcode_url == p["leetcode_url"],
                    IP.company == p["company"],
                    IP.recency == p["recency"],
                )
            ).first()
            if existing:
                continue

            session.add(InterviewProblem(**p))
            total_new += 1

        session.commit()

    return total_new


def _fetch_csv_content(download_url: str) -> str:
    """Fetch raw CSV text from GitHub."""
    resp = httpx.get(download_url, timeout=15)
    resp.raise_for_status()
    return resp.text


def _parse_csv(csv_text: str, company: str, recency: str) -> list[dict]:
    """Parse CSV text into list of dicts matching InterviewProblem fields."""
    reader = csv.DictReader(io.StringIO(csv_text))
    problems = []
    for row in reader:
        title = row.get("Title", "").strip()
        link = row.get("Link", "").strip()
        if not title or not link:
            continue

        try:
            frequency = float(row.get("Frequency", 0))
        except (ValueError, TypeError):
            frequency = 0.0

        try:
            acceptance = float(row.get("Acceptance Rate", 0))
        except (ValueError, TypeError):
            acceptance = 0.0

        problems.append({
            "title": title,
            "difficulty": row.get("Difficulty", "").strip().capitalize(),
            "frequency": frequency,
            "acceptance_rate": acceptance,
            "leetcode_url": link,
            "topics": row.get("Topics", "").strip(),
            "company": company,
            "recency": recency,
        })
    return problems


def _load_config(config_path: str = "config.yaml") -> dict:
    """Load config from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)
