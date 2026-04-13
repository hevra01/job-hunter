"""
Scraper for configurable lab/institute websites.
Uses httpx for static pages, Playwright for JS-heavy ones.
"""
import logging
import re
from typing import Optional
from .base import BaseScraper, RawJob, classify_job_type, extract_email, clean_text

logger = logging.getLogger(__name__)

# Keywords that signal a link is a job/opening listing
OPENING_LINK_KEYWORDS = re.compile(
    r"(position|opening|vacancy|job|phd|postdoc|fellowship|apply|opportunit|recruit)",
    re.IGNORECASE,
)


class LabWebsiteScraper(BaseScraper):
    name = "lab_website"

    def __init__(self, labs: list[dict]):
        self.labs = labs

    def _scrape_lab(self, lab: dict) -> list[RawJob]:
        name = lab["name"]
        openings_url = lab.get("openings_url") or lab["url"]
        js_required = lab.get("js_required", False)

        if js_required:
            return self._scrape_with_playwright(name, openings_url)
        return self._scrape_static(name, openings_url)

    def _scrape_static(self, org_name: str, url: str) -> list[RawJob]:
        soup = self.fetch(url)
        if not soup:
            return []

        jobs: list[RawJob] = []
        # Look for links that sound like job postings
        for link in soup.find_all("a", href=True):
            text = clean_text(link.get_text())
            href = link["href"]

            if not text or len(text) < 5:
                continue

            # Check if the anchor text OR href looks like a job link
            if not (OPENING_LINK_KEYWORDS.search(text) or OPENING_LINK_KEYWORDS.search(href)):
                continue

            job_url = href if href.startswith("http") else self._make_absolute(url, href)
            if not job_url:
                continue

            # Fetch the linked page for the description
            detail = self.fetch(job_url)
            description = ""
            contact_email = None
            if detail:
                # Remove nav/footer noise
                for tag in detail.select("nav, footer, header, script, style"):
                    tag.decompose()
                main = detail.select_one("main, article, .content, #content, body")
                if main:
                    description = clean_text(main.get_text())
                contact_email = extract_email(detail.get_text())

            jobs.append(RawJob(
                title=text[:200],
                organization=org_name,
                url=job_url,
                description=description or text,
                job_type=classify_job_type(text, description),
                source=self.name,
                application_method="email" if contact_email else "form",
                contact_email=contact_email,
            ))

        return jobs

    def _scrape_with_playwright(self, org_name: str, url: str) -> list[RawJob]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed; skipping JS-required lab: %s", org_name)
            return []

        jobs: list[RawJob] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)
                content = page.content()
                browser.close()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")
            for tag in soup.select("nav, footer, header, script, style"):
                tag.decompose()

            for link in soup.find_all("a", href=True):
                text = clean_text(link.get_text())
                href = link["href"]
                if not text or len(text) < 5:
                    continue
                if not (OPENING_LINK_KEYWORDS.search(text) or OPENING_LINK_KEYWORDS.search(href)):
                    continue
                job_url = href if href.startswith("http") else self._make_absolute(url, href)
                if not job_url:
                    continue
                jobs.append(RawJob(
                    title=text[:200],
                    organization=org_name,
                    url=job_url,
                    description=text,
                    job_type=classify_job_type(text, ""),
                    source=self.name,
                ))
        except Exception as e:
            logger.error("Playwright scrape failed for %s: %s", org_name, e)

        return jobs

    @staticmethod
    def _make_absolute(base_url: str, href: str) -> Optional[str]:
        if href.startswith("//"):
            scheme = base_url.split("://")[0]
            return f"{scheme}:{href}"
        if href.startswith("/"):
            parts = base_url.split("/")
            return f"{parts[0]}//{parts[2]}{href}"
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            return None
        # relative path
        base = base_url.rstrip("/")
        return f"{base}/{href}"

    def scrape(self) -> list[RawJob]:
        jobs = []
        for lab in self.labs:
            logger.info("[lab_website] Scraping %s", lab["name"])
            try:
                found = self._scrape_lab(lab)
                jobs.extend(found)
            except Exception as e:
                logger.error("[lab_website] Failed for %s: %s", lab["name"], e)
        return jobs
