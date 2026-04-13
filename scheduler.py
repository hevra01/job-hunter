"""
Periodic job discovery pipeline.
Runs all scrapers, scores results with Claude, generates cover letters,
and saves new jobs to the database.
"""
import logging
import os
from datetime import datetime
from pathlib import Path

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from models import Job, Application, create_tables, engine, job_exists
from scrapers.academic_boards import EuraxessScraper, AcademicPositionsScraper, JobsAcUkScraper
from scrapers.lab_websites import LabWebsiteScraper
from scrapers.company_careers import build_company_scrapers
from scrapers.linkedin import LinkedInScraper
from ai.scorer import score_job
from ai.cover_letter import generate_cover_letter

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def build_scrapers(cfg: dict) -> list:
    scrapers = []

    boards = cfg.get("academic_boards", {})

    if boards.get("euraxess", {}).get("enabled", True):
        terms = boards["euraxess"].get("search_terms", ["machine learning"])
        scrapers.append(EuraxessScraper(terms))

    if boards.get("academic_positions", {}).get("enabled", True):
        terms = boards["academic_positions"].get("search_terms", ["machine learning"])
        scrapers.append(AcademicPositionsScraper(terms))

    if boards.get("jobs_ac_uk", {}).get("enabled", True):
        terms = boards["jobs_ac_uk"].get("search_terms", ["machine learning"])
        scrapers.append(JobsAcUkScraper(terms))

    labs = cfg.get("labs", [])
    if labs:
        scrapers.append(LabWebsiteScraper(labs))

    companies = cfg.get("companies", [])
    scrapers.extend(build_company_scrapers(companies))

    li_cfg = cfg.get("linkedin", {})
    if li_cfg.get("enabled", False):
        scrapers.append(LinkedInScraper(
            search_queries=li_cfg.get("search_queries", []),
            location=li_cfg.get("location_filter", "Europe"),
            cookies_file=li_cfg.get("cookies_file", "data/linkedin_cookies.json"),
        ))

    return scrapers


def run_discovery(config_path: str = "config.yaml") -> dict:
    """
    Main pipeline: scrape → score → generate cover letter → save to DB.
    Returns summary stats.
    """
    cfg = load_config(config_path)
    min_score = cfg.get("targets", {}).get("min_relevance_score", 60)

    scrapers = build_scrapers(cfg)
    stats = {"scraped": 0, "new": 0, "above_threshold": 0, "errors": 0}

    all_raw_jobs = []
    for scraper in scrapers:
        raw = scraper.run()
        all_raw_jobs.extend(raw)
        stats["scraped"] += len(raw)

    logger.info("Total raw jobs collected: %d", len(all_raw_jobs))

    with Session(engine) as session:
        for raw in all_raw_jobs:
            try:
                # Skip duplicates
                if job_exists(session, raw.url):
                    continue

                stats["new"] += 1

                # Score with keyword matching
                score_result = score_job(
                    title=raw.title,
                    organization=raw.organization,
                    description=raw.description,
                )

                score = score_result["score"]
                reasoning = score_result["reasoning"]
                job_type = score_result.get("job_type_detected", raw.job_type)
                include_rec = score_result.get("include_recommendation_letter", False)

                # Save the job regardless of score (for record keeping)
                job = Job(
                    title=raw.title,
                    organization=raw.organization,
                    url=raw.url,
                    description=raw.description,
                    job_type=job_type,
                    source=raw.source,
                    relevance_score=score,
                    relevance_reasoning=reasoning,
                    application_method=raw.application_method,
                    contact_email=raw.contact_email,
                    status="new" if score < min_score else "queued",
                )
                session.add(job)
                session.flush()  # get job.id

                if score >= min_score:
                    stats["above_threshold"] += 1

                    # Generate editable cover letter template (no AI)
                    cover_letter = generate_cover_letter(
                        title=raw.title,
                        organization=raw.organization,
                        description=raw.description,
                        job_type=job_type,
                    )

                    application = Application(
                        job_id=job.id,
                        cover_letter=cover_letter,
                        include_cv=True,
                        include_recommendation=include_rec,
                        send_method=raw.application_method,
                    )
                    session.add(application)

                session.commit()
                logger.info(
                    "[%s] %s @ %s → score=%d, status=%s",
                    raw.source, raw.title, raw.organization, score, job.status,
                )

            except Exception as e:
                stats["errors"] += 1
                logger.error("Error processing job '%s': %s", raw.title, e)
                session.rollback()

    logger.info(
        "Discovery complete. Scraped=%d New=%d Above-threshold=%d Errors=%d",
        stats["scraped"], stats["new"], stats["above_threshold"], stats["errors"],
    )
    return stats


def start_scheduler(config_path: str = "config.yaml") -> BackgroundScheduler:
    """Start the background scheduler based on config interval."""
    cfg = load_config(config_path)
    interval_str = cfg.get("scraping_interval", "24h")

    # Parse interval string: "6h", "12h", "24h"
    hours = int(interval_str.replace("h", "").strip()) if "h" in interval_str else 24

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=run_discovery,
        trigger="interval",
        hours=hours,
        id="job_discovery",
        next_run_time=datetime.now(),  # run immediately on startup
        kwargs={"config_path": config_path},
    )
    scheduler.start()
    logger.info("Scheduler started: running discovery every %dh", hours)
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    create_tables()
    logger.info("Running one-shot discovery...")
    stats = run_discovery()
    print(f"Done: {stats}")
