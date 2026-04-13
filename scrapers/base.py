import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class RawJob:
    title: str
    organization: str
    url: str
    description: str
    job_type: str          # phd | research_scientist | ml_engineer | postdoc | other
    source: str
    application_method: str = "form"   # email | form | unknown
    contact_email: Optional[str] = None


def classify_job_type(title: str, description: str) -> str:
    text = (title + " " + description).lower()
    if any(kw in text for kw in ["phd", "ph.d", "doctoral", "doctorate"]):
        return "phd"
    if any(kw in text for kw in ["postdoc", "post-doc", "post doctoral", "postdoctoral"]):
        return "postdoc"
    if any(kw in text for kw in ["research scientist", "research engineer", "research intern", "research fellow"]):
        return "research_scientist"
    if any(kw in text for kw in ["machine learning engineer", "ml engineer", "ai engineer", "deep learning engineer"]):
        return "ml_engineer"
    return "other"


def extract_email(text: str) -> Optional[str]:
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


def clean_text(text: str) -> str:
    """Strip excessive whitespace from scraped text."""
    return re.sub(r"\s+", " ", text).strip()


class BaseScraper(ABC):
    name: str = "base"

    def fetch(self, url: str, timeout: int = 20) -> Optional[BeautifulSoup]:
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to fetch {url}: {e}")
            return None

    @abstractmethod
    def scrape(self) -> list[RawJob]:
        """Return a list of RawJob objects."""
        ...

    def run(self) -> list[RawJob]:
        logger.info(f"[{self.name}] Starting scrape...")
        try:
            jobs = self.scrape()
            logger.info(f"[{self.name}] Found {len(jobs)} jobs")
            return jobs
        except Exception as e:
            logger.error(f"[{self.name}] Scrape failed: {e}", exc_info=True)
            return []
