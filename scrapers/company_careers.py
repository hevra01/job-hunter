"""
Scrapers for major industry AI company career pages.
Uses the Greenhouse JSON API where available, falls back to HTML scraping.
"""
import logging
import httpx
from .base import BaseScraper, RawJob, classify_job_type, extract_email, clean_text

logger = logging.getLogger(__name__)


class GreenhouseScraper(BaseScraper):
    """Works for any company using Greenhouse (DeepMind, etc.)."""
    name = "greenhouse"
    API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

    def __init__(self, company_name: str, board_id: str, keywords: list[str], company_tier: str = ""):
        self.company_name = company_name
        self.board_id = board_id
        self.keywords = [k.lower() for k in keywords]
        self.company_tier = company_tier

    def scrape(self) -> list[RawJob]:
        try:
            resp = httpx.get(self.API.format(board=self.board_id), timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("[greenhouse:%s] API failed: %s", self.board_id, e)
            return []

        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title", "")
            description = clean_text(item.get("content", ""))
            text = (title + " " + description).lower()

            if not any(kw in text for kw in self.keywords):
                continue

            job_url = item.get("absolute_url", "")
            jobs.append(RawJob(
                title=title,
                organization=self.company_name,
                url=job_url,
                description=description,
                job_type=classify_job_type(title, description),
                source=f"greenhouse:{self.board_id}",
                application_method="form",
                company_tier=self.company_tier,
            ))

        return jobs


class MetaAIScraper(BaseScraper):
    name = "meta_ai"
    # Meta has a GraphQL/JSON API for job search
    SEARCH_URL = (
        "https://www.metacareers.com/graphql"
    )

    def __init__(self, keywords: list[str], company_tier: str = ""):
        self.keywords = keywords
        self.company_tier = company_tier

    def scrape(self) -> list[RawJob]:
        # Meta's careers page requires JS; fall back to static search API
        jobs = []
        for keyword in self.keywords:
            try:
                url = f"https://www.metacareers.com/jobs?q={keyword.replace(' ', '+')}&divisions[0]=Artificial+Intelligence&offices[0]=Europe"
                soup = self.fetch(url)
                if not soup:
                    continue

                for item in soup.select("a[href*='/jobs/']"):
                    title = clean_text(item.get_text())
                    if len(title) < 5:
                        continue
                    href = item.get("href", "")
                    job_url = href if href.startswith("http") else "https://www.metacareers.com" + href

                    kw_lower = keyword.lower()
                    if kw_lower not in title.lower():
                        continue

                    jobs.append(RawJob(
                        title=title,
                        organization="Meta AI",
                        url=job_url,
                        description=title,  # full desc needs JS
                        job_type=classify_job_type(title, ""),
                        source=self.name,
                        application_method="form",
                        company_tier=self.company_tier,
                    ))
            except Exception as e:
                logger.debug("[meta_ai] %s: %s", keyword, e)

        return jobs


class MicrosoftResearchScraper(BaseScraper):
    name = "microsoft_research"
    SEARCH_URL = (
        "https://careers.microsoft.com/v2/global/en/search.html"
        "?q={query}&lc=United+States,United+Kingdom,Germany,Netherlands,France&l=en_us&pgNum={page}"
    )

    def __init__(self, keywords: list[str], company_tier: str = ""):
        self.keywords = keywords
        self.company_tier = company_tier

    def scrape(self) -> list[RawJob]:
        jobs = []
        seen = set()
        for kw in self.keywords:
            for page in range(1, 3):
                url = self.SEARCH_URL.format(query=kw.replace(" ", "+"), page=page)
                soup = self.fetch(url)
                if not soup:
                    break

                for item in soup.select("a[href*='/jobs/']"):
                    title = clean_text(item.get_text())
                    if len(title) < 5 or title in seen:
                        continue
                    seen.add(title)
                    href = item.get("href", "")
                    job_url = href if href.startswith("http") else "https://careers.microsoft.com" + href

                    jobs.append(RawJob(
                        title=title,
                        organization="Microsoft Research",
                        url=job_url,
                        description=title,
                        job_type=classify_job_type(title, ""),
                        source=self.name,
                        application_method="form",
                        company_tier=self.company_tier,
                    ))

        return jobs


class NvidiaResearchScraper(BaseScraper):
    name = "nvidia_research"
    SEARCH_URL = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"

    def __init__(self, keywords: list[str], company_tier: str = ""):
        self.keywords = keywords
        self.company_tier = company_tier

    def scrape(self) -> list[RawJob]:
        jobs = []
        for kw in self.keywords:
            try:
                payload = {
                    "appliedFacets": {"workerSubType": []},
                    "limit": 20,
                    "offset": 0,
                    "searchText": kw,
                }
                resp = httpx.post(
                    self.SEARCH_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=20,
                )
                data = resp.json()
                for item in data.get("jobPostings", []):
                    title = item.get("title", "")
                    ext_id = item.get("externalPath", "")
                    job_url = f"https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite{ext_id}"
                    jobs.append(RawJob(
                        title=title,
                        organization="NVIDIA Research",
                        url=job_url,
                        description=title,
                        job_type=classify_job_type(title, ""),
                        source=self.name,
                        application_method="form",
                        company_tier=self.company_tier,
                    ))
            except Exception as e:
                logger.debug("[nvidia] %s: %s", kw, e)

        return jobs


def build_company_scrapers(companies: list[dict]) -> list[BaseScraper]:
    """Build scraper instances from config.yaml companies list."""
    scrapers = []
    for co in companies:
        portal = co.get("portal", "generic")
        name = co["name"]
        keywords = co.get("search_terms", ["machine learning"])
        tier = co.get("tier", "")

        if portal == "greenhouse":
            board = co.get("greenhouse_board", "")
            if board:
                scrapers.append(GreenhouseScraper(name, board, keywords, company_tier=tier))
        elif portal == "meta":
            scrapers.append(MetaAIScraper(keywords, company_tier=tier))
        elif portal == "microsoft":
            scrapers.append(MicrosoftResearchScraper(keywords, company_tier=tier))
        elif portal == "nvidia" or (portal == "generic" and "nvidia" in name.lower()):
            scrapers.append(NvidiaResearchScraper(keywords, company_tier=tier))
        else:
            logger.debug("No dedicated scraper for %s (portal=%s); skipping", name, portal)

    return scrapers
