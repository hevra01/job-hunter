"""
Scrapers for academic job boards:
- Euraxess (euraxess.ec.europa.eu)
- Academic Positions (academicpositions.eu)
- jobs.ac.uk
"""
import logging
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper, RawJob, classify_job_type, extract_email, clean_text

logger = logging.getLogger(__name__)


class EuraxessScraper(BaseScraper):
    name = "euraxess"
    BASE = "https://euraxess.ec.europa.eu"
    SEARCH_URL = (
        "https://euraxess.ec.europa.eu/jobs/search"
        "?keywords={query}&research_field=computer+science"
        "&page={page}"
    )

    def __init__(self, search_terms: list[str]):
        self.search_terms = search_terms

    def scrape(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen_urls: set[str] = set()

        for term in self.search_terms:
            for page in range(0, 3):  # pages 0,1,2 → up to ~60 results per term
                url = self.SEARCH_URL.format(query=term.replace(" ", "+"), page=page)
                soup = self.fetch(url)
                if not soup:
                    break

                listings = soup.select("div.views-row")
                if not listings:
                    break

                for item in listings:
                    try:
                        title_el = item.select_one("h3.title a, .job-title a")
                        if not title_el:
                            continue
                        title = clean_text(title_el.get_text())
                        href = title_el.get("href", "")
                        job_url = href if href.startswith("http") else self.BASE + href

                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        org_el = item.select_one(".organisation-name, .field-name-field-euraxess-org-name")
                        org = clean_text(org_el.get_text()) if org_el else "Unknown"

                        # Fetch detail page for full description
                        detail = self.fetch(job_url)
                        description = ""
                        contact_email = None
                        if detail:
                            body = detail.select_one(".field-name-body, .job-description, article .field")
                            if body:
                                description = clean_text(body.get_text())
                            contact_email = extract_email(detail.get_text())

                        jobs.append(RawJob(
                            title=title,
                            organization=org,
                            url=job_url,
                            description=description or title,
                            job_type=classify_job_type(title, description),
                            source=self.name,
                            application_method="email" if contact_email else "form",
                            contact_email=contact_email,
                        ))
                    except Exception as e:
                        logger.debug(f"[euraxess] Error parsing item: {e}")

        return jobs


class AcademicPositionsScraper(BaseScraper):
    name = "academic_positions"
    BASE = "https://academicpositions.eu"
    SEARCH_URL = "https://academicpositions.eu/jobs?keywords={query}&page={page}"

    def __init__(self, search_terms: list[str]):
        self.search_terms = search_terms

    def scrape(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen_urls: set[str] = set()

        for term in self.search_terms:
            for page in range(1, 4):
                url = self.SEARCH_URL.format(query=term.replace(" ", "+"), page=page)
                soup = self.fetch(url)
                if not soup:
                    break

                listings = soup.select("article.job-item, div.job-listing, .position-item")
                if not listings:
                    # Try generic link scan
                    listings = soup.select("a[href*='/ad/']")

                if not listings:
                    break

                for item in listings:
                    try:
                        # Handle both article and direct link cases
                        if item.name == "a":
                            title = clean_text(item.get_text())
                            href = item.get("href", "")
                        else:
                            link = item.select_one("a[href*='/ad/'], h2 a, h3 a, .job-title a")
                            if not link:
                                continue
                            title = clean_text(link.get_text())
                            href = link.get("href", "")

                        job_url = href if href.startswith("http") else self.BASE + href
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        org_el = item.select_one(".university-name, .employer, .institution")
                        org = clean_text(org_el.get_text()) if org_el else "Unknown"

                        detail = self.fetch(job_url)
                        description = ""
                        contact_email = None
                        if detail:
                            body = detail.select_one(".job-body, .description, article .content, main")
                            if body:
                                description = clean_text(body.get_text())
                            contact_email = extract_email(detail.get_text())

                        jobs.append(RawJob(
                            title=title,
                            organization=org,
                            url=job_url,
                            description=description or title,
                            job_type=classify_job_type(title, description),
                            source=self.name,
                            application_method="email" if contact_email else "form",
                            contact_email=contact_email,
                        ))
                    except Exception as e:
                        logger.debug(f"[academic_positions] Error parsing item: {e}")

        return jobs


class JobsAcUkScraper(BaseScraper):
    name = "jobs_ac_uk"
    BASE = "https://www.jobs.ac.uk"
    SEARCH_URL = (
        "https://www.jobs.ac.uk/search/?keywords={query}"
        "&location=&employmentType=&subjectArea=computer-science"
        "&startIndex={start}"
    )

    def __init__(self, search_terms: list[str]):
        self.search_terms = search_terms

    def scrape(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen_urls: set[str] = set()

        for term in self.search_terms:
            for page_idx in range(3):  # 0, 25, 50
                start = page_idx * 25
                url = self.SEARCH_URL.format(query=term.replace(" ", "+"), start=start)
                soup = self.fetch(url)
                if not soup:
                    break

                listings = soup.select("div.j-search-result__text, article.j-search-result")
                if not listings:
                    break

                for item in listings:
                    try:
                        title_el = item.select_one("a.j-search-result__job-title, h2 a, .job-title a")
                        if not title_el:
                            continue
                        title = clean_text(title_el.get_text())
                        href = title_el.get("href", "")
                        job_url = href if href.startswith("http") else self.BASE + href

                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        org_el = item.select_one(".j-search-result__employer, .employer-name")
                        org = clean_text(org_el.get_text()) if org_el else "Unknown"

                        detail = self.fetch(job_url)
                        description = ""
                        contact_email = None
                        if detail:
                            body = detail.select_one("#job-description, .job-description, .description-content")
                            if body:
                                description = clean_text(body.get_text())
                            contact_email = extract_email(detail.get_text())

                        jobs.append(RawJob(
                            title=title,
                            organization=org,
                            url=job_url,
                            description=description or title,
                            job_type=classify_job_type(title, description),
                            source=self.name,
                            application_method="email" if contact_email else "form",
                            contact_email=contact_email,
                        ))
                    except Exception as e:
                        logger.debug(f"[jobs_ac_uk] Error parsing item: {e}")

        return jobs
