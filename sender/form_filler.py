"""
Playwright-based form filler for online job application portals.

Supports:
- Greenhouse (boards.greenhouse.io)
- Lever (jobs.lever.co)
- Generic (best-effort by label matching)

Workday is complex and not auto-filled — flagged for manual completion.
"""
import logging
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ApplicantInfo:
    first_name: str
    last_name: str
    email: str
    phone: str
    cover_letter: str
    cv_path: str
    linkedin_url: str = ""
    github_url: str = "https://github.com/hevra01"


def _detect_portal(url: str) -> str:
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "myworkdayjobs.com" in url or "wd1.myworkdayjobs" in url or "wd5.myworkdayjobs" in url:
        return "workday"
    return "generic"


def fill_greenhouse(page, info: ApplicantInfo) -> bool:
    """Fill a Greenhouse application form."""
    try:
        # Basic fields
        _fill_if_exists(page, "#first_name", info.first_name)
        _fill_if_exists(page, "#last_name", info.last_name)
        _fill_if_exists(page, "#email", info.email)
        _fill_if_exists(page, "#phone", info.phone)

        # Upload CV
        if Path(info.cv_path).exists():
            file_input = page.query_selector("input[type='file'][name*='resume'], input[type='file'][id*='resume']")
            if file_input:
                file_input.set_input_files(info.cv_path)
                logger.info("[greenhouse] Uploaded CV")

        # Cover letter (text area or file upload)
        cl_textarea = page.query_selector("textarea[name*='cover'], textarea[id*='cover'], textarea[name*='letter']")
        if cl_textarea:
            cl_textarea.fill(info.cover_letter)

        # LinkedIn / GitHub fields
        _fill_if_exists(page, "input[name*='linkedin'], input[id*='linkedin']", info.linkedin_url)
        _fill_if_exists(page, "input[name*='github'], input[id*='github']", info.github_url)

        logger.info("[greenhouse] Form filled successfully")
        return True
    except Exception as e:
        logger.error("[greenhouse] Fill error: %s", e)
        return False


def fill_lever(page, info: ApplicantInfo) -> bool:
    """Fill a Lever application form."""
    try:
        _fill_if_exists(page, "input[name='name']", f"{info.first_name} {info.last_name}")
        _fill_if_exists(page, "input[name='email']", info.email)
        _fill_if_exists(page, "input[name='phone']", info.phone)

        if Path(info.cv_path).exists():
            file_input = page.query_selector("input[type='file']")
            if file_input:
                file_input.set_input_files(info.cv_path)

        _fill_if_exists(page, "textarea[name='comments'], textarea[name='cover_letter']", info.cover_letter)
        _fill_if_exists(page, "input[name*='linkedin']", info.linkedin_url)

        logger.info("[lever] Form filled successfully")
        return True
    except Exception as e:
        logger.error("[lever] Fill error: %s", e)
        return False


def fill_generic(page, info: ApplicantInfo) -> bool:
    """Best-effort generic form filling by label/placeholder matching."""
    try:
        filled = 0
        for inp in page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], textarea"):
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            name = (inp.get_attribute("name") or "").lower()
            id_ = (inp.get_attribute("id") or "").lower()
            combined = placeholder + name + id_

            value = None
            if any(k in combined for k in ["first", "fname", "given"]):
                value = info.first_name
            elif any(k in combined for k in ["last", "lname", "family", "surname"]):
                value = info.last_name
            elif "email" in combined:
                value = info.email
            elif any(k in combined for k in ["phone", "mobile", "tel"]):
                value = info.phone
            elif any(k in combined for k in ["cover", "letter", "motivation", "message"]):
                value = info.cover_letter
            elif "linkedin" in combined:
                value = info.linkedin_url
            elif "github" in combined:
                value = info.github_url

            if value:
                inp.fill(value)
                filled += 1

        if Path(info.cv_path).exists():
            file_inputs = page.query_selector_all("input[type='file']")
            if file_inputs:
                file_inputs[0].set_input_files(info.cv_path)
                filled += 1

        logger.info("[generic] Filled %d fields", filled)
        return filled > 0
    except Exception as e:
        logger.error("[generic] Fill error: %s", e)
        return False


def _fill_if_exists(page, selector: str, value: str):
    """Fill the first matching element if it exists."""
    if not value:
        return
    el = page.query_selector(selector)
    if el:
        el.fill(value)


def submit_form_application(
    job_url: str,
    info: ApplicantInfo,
    dry_run: bool = False,
) -> dict:
    """
    Navigate to a job application URL and fill the form.

    Returns:
        {
            "success": bool,
            "portal": str,
            "message": str,
            "needs_manual": bool,
        }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "portal": "unknown", "message": "Playwright not installed", "needs_manual": True}

    portal = _detect_portal(job_url)

    if portal == "workday":
        return {
            "success": False,
            "portal": "workday",
            "message": "Workday portals require manual application — too complex to auto-fill reliably.",
            "needs_manual": True,
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not dry_run)
        page = browser.new_page()

        try:
            page.goto(job_url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Navigate to the actual application form if needed
            apply_btn = page.query_selector(
                "a[href*='apply'], button:has-text('Apply'), a:has-text('Apply Now'), "
                "a:has-text('Apply for this job')"
            )
            if apply_btn:
                apply_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)

            if portal == "greenhouse":
                success = fill_greenhouse(page, info)
            elif portal == "lever":
                success = fill_lever(page, info)
            else:
                success = fill_generic(page, info)

            if success and not dry_run:
                # Try to click submit
                submit_btn = page.query_selector(
                    "button[type='submit'], input[type='submit'], "
                    "button:has-text('Submit'), button:has-text('Apply')"
                )
                if submit_btn:
                    submit_btn.click()
                    page.wait_for_load_state("networkidle", timeout=10000)
                    logger.info("[form_filler] Form submitted at %s", job_url)

            browser.close()
            return {
                "success": success,
                "portal": portal,
                "message": "Form filled and submitted" if success else "Partial fill — check manually",
                "needs_manual": not success,
            }

        except Exception as e:
            browser.close()
            logger.error("[form_filler] Error at %s: %s", job_url, e)
            return {
                "success": False,
                "portal": portal,
                "message": str(e),
                "needs_manual": True,
            }
