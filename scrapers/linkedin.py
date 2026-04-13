"""
LinkedIn Jobs scraper using Playwright + user session cookies.
LinkedIn aggressively blocks bots, so this is best-effort and may require
periodic cookie refresh.

Setup: Log into LinkedIn in Chrome, export cookies to data/linkedin_cookies.json
using a browser extension like "Cookie-Editor", then set linkedin.enabled=true in config.yaml.
"""
import json
import logging
import os
from pathlib import Path
from .base import BaseScraper, RawJob, classify_job_type, extract_email, clean_text

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords={query}&location={location}&f_TPR=r86400"  # last 24h
)


class LinkedInScraper(BaseScraper):
    name = "linkedin"

    def __init__(self, search_queries: list[str], location: str, cookies_file: str):
        self.search_queries = search_queries
        self.location = location
        self.cookies_file = cookies_file

    def _load_cookies(self) -> list[dict]:
        path = Path(self.cookies_file)
        if not path.exists():
            raise FileNotFoundError(
                f"LinkedIn cookies file not found: {self.cookies_file}. "
                "Export cookies from your browser after logging into LinkedIn."
            )
        with open(path) as f:
            return json.load(f)

    def scrape(self) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        try:
            cookies = self._load_cookies()
        except FileNotFoundError as e:
            logger.warning("[linkedin] %s", e)
            return []

        jobs = []
        seen_urls: set[str] = set()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                # Inject session cookies
                context.add_cookies(cookies)
                page = context.new_page()

                for query in self.search_queries:
                    try:
                        url = SEARCH_URL.format(
                            query=query.replace(" ", "%20"),
                            location=self.location.replace(" ", "%20"),
                        )
                        page.goto(url, timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=15000)

                        # Scroll to load more results
                        for _ in range(3):
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            page.wait_for_timeout(1500)

                        items = page.query_selector_all("li.jobs-search-results__list-item")
                        for item in items:
                            try:
                                title_el = item.query_selector("a.job-card-list__title, a[data-tracking-control-name='public_jobs_jserp-result_search-card']")
                                if not title_el:
                                    continue
                                title = clean_text(title_el.inner_text())
                                job_url = title_el.get_attribute("href") or ""
                                if "?" in job_url:
                                    job_url = job_url.split("?")[0]

                                if job_url in seen_urls:
                                    continue
                                seen_urls.add(job_url)

                                org_el = item.query_selector(".job-card-container__company-name, .artdeco-entity-lockup__subtitle")
                                org = clean_text(org_el.inner_text()) if org_el else "Unknown"

                                # Click to load description in side panel
                                title_el.click()
                                page.wait_for_timeout(2000)
                                desc_el = page.query_selector(".jobs-description__content, .job-view-layout")
                                description = clean_text(desc_el.inner_text()) if desc_el else title
                                contact_email = extract_email(description)

                                jobs.append(RawJob(
                                    title=title,
                                    organization=org,
                                    url=job_url,
                                    description=description,
                                    job_type=classify_job_type(title, description),
                                    source=self.name,
                                    application_method="form",
                                    contact_email=contact_email,
                                ))
                            except Exception as e:
                                logger.debug("[linkedin] item error: %s", e)

                    except Exception as e:
                        logger.warning("[linkedin] query '%s' failed: %s", query, e)

                browser.close()

        except Exception as e:
            logger.error("[linkedin] Playwright session failed: %s", e)

        return jobs
