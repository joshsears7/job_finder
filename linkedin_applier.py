"""
linkedin_applier.py
-------------------
Agentic LinkedIn Easy Apply: finds matching Easy Apply jobs and submits
applications with AI-generated cover letters, human-in-the-loop confirmation
before every submission.

Requires: pip install playwright && python -m playwright install chromium

IMPORTANT: Use this tool responsibly. Apply only to jobs you genuinely want.
Automated applications sent in bulk at speed are against LinkedIn's Terms of
Service and will result in account restrictions. This tool enforces:
- Per-apply human confirmation (you see and approve each application)
- Minimum 30s delay between submissions to avoid rate detection
- Session-level caps (default 20 applications per session max)
"""

import os
import re
import time
import json
import logging
from datetime import datetime
from typing import Generator

_log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────
_MIN_DELAY_SEC  = 30
_MAX_PER_SESSION = 20
_LINKEDIN_BASE  = "https://www.linkedin.com"

# ── Credential helpers ────────────────────────────────────────────

def get_credentials() -> tuple[str, str]:
    """Return (email, password) from env vars or raise."""
    email    = os.getenv("LINKEDIN_EMAIL", "")
    password = os.getenv("LINKEDIN_PASSWORD", "")
    if not email or not password:
        raise EnvironmentError(
            "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in your .env file. "
            "These are never logged or transmitted anywhere — only used locally by Playwright."
        )
    return email, password


# ── Browser session ────────────────────────────────────────────────

class LinkedInSession:
    """
    Manages a Playwright browser session for LinkedIn interaction.
    Always uses non-headless mode so the user can see what's happening.
    """

    def __init__(self, slow_mo: int = 400):
        self._slow_mo = slow_mo
        self._pw = None
        self._browser = None
        self._page = None
        self._logged_in = False

    def start(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(headless=False, slow_mo=self._slow_mo)
        context       = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = context.new_page()
        return self

    def stop(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()

    @property
    def page(self):
        return self._page

    def login(self) -> bool:
        """Log into LinkedIn. Returns True on success."""
        email, password = get_credentials()
        page = self._page

        page.goto(f"{_LINKEDIN_BASE}/login", wait_until="networkidle")
        time.sleep(1)

        try:
            page.fill("#username", email)
            page.fill("#password", password)
            page.click('[type="submit"]')
            page.wait_for_url(re.compile(r"/feed|/in/"), timeout=15000)
            self._logged_in = True
            _log.info("Logged in to LinkedIn")
            return True
        except Exception as e:
            _log.error("Login failed: %s", e)
            return False

    def search_easy_apply_jobs(
        self,
        role: str,
        location: str = "",
        filters: dict = None,
        max_results: int = 50,
    ) -> list[dict]:
        """
        Search LinkedIn for Easy Apply jobs matching role + location.
        Returns list of {title, company, location, url, job_id}.
        """
        if not self._logged_in:
            raise RuntimeError("Call login() first.")

        filters = filters or {}
        page    = self._page

        # Build search URL
        params = {
            "keywords": role,
            "f_AL":     "true",  # Easy Apply only
        }
        if location:
            params["location"] = location
        if filters.get("experience"):
            params["f_E"] = filters["experience"]  # 1=internship, 2=entry, 3=associate
        if filters.get("date_posted"):
            params["f_TPR"] = filters["date_posted"]  # r86400=24h, r604800=week

        query = "&".join(f"{k}={v}" for k, v in params.items())
        page.goto(
            f"{_LINKEDIN_BASE}/jobs/search/?{query}",
            wait_until="domcontentloaded",
        )
        time.sleep(2)

        jobs = []
        seen = set()

        for _ in range(max_results // 10 + 1):
            if len(jobs) >= max_results:
                break

            # Collect job cards on current page
            cards = page.query_selector_all(".job-card-container")
            for card in cards:
                try:
                    title_el   = card.query_selector(".job-card-list__title")
                    company_el = card.query_selector(".job-card-container__company-name")
                    loc_el     = card.query_selector(".job-card-container__metadata-item")
                    link_el    = card.query_selector("a.job-card-container__link")

                    if not title_el or not link_el:
                        continue

                    href    = link_el.get_attribute("href") or ""
                    job_id  = re.search(r"/jobs/view/(\d+)", href)
                    job_id  = job_id.group(1) if job_id else href[-20:]

                    if job_id in seen:
                        continue
                    seen.add(job_id)

                    jobs.append({
                        "title":    title_el.inner_text().strip(),
                        "company":  company_el.inner_text().strip() if company_el else "Unknown",
                        "location": loc_el.inner_text().strip() if loc_el else location,
                        "url":      f"{_LINKEDIN_BASE}{href}" if href.startswith("/") else href,
                        "job_id":   job_id,
                    })
                except Exception:
                    continue

            # Try to go to next page
            next_btn = page.query_selector('button[aria-label="Next"]')
            if not next_btn or not next_btn.is_enabled():
                break
            next_btn.click()
            time.sleep(2)

        return jobs[:max_results]

    def get_job_description(self, job_url: str) -> str:
        """Navigate to a job and return its description text."""
        self._page.goto(job_url, wait_until="domcontentloaded")
        time.sleep(1)
        try:
            el = self._page.query_selector(".jobs-description__content")
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""

    def apply_to_job(
        self,
        job: dict,
        profile: dict,
        cover_letter: str = "",
        dry_run: bool = True,
    ) -> dict:
        """
        Submit an Easy Apply application for one job.
        dry_run=True: fills forms but does NOT click final Submit.
        Returns {success, steps_completed, message}.
        """
        page = self._page
        try:
            page.goto(job["url"], wait_until="domcontentloaded")
            time.sleep(1.5)

            # Click "Easy Apply" button
            easy_btn = page.query_selector('button.jobs-apply-button')
            if not easy_btn:
                return {"success": False, "message": "No Easy Apply button found"}
            easy_btn.click()
            time.sleep(1.5)

            steps_completed = 0

            # Handle multi-step form (up to 10 steps)
            for step in range(10):
                # Fill text inputs if they map to known profile fields
                inputs = page.query_selector_all("input[type='text'], input[type='tel'], input[type='email']")
                for inp in inputs:
                    label_text = ""
                    try:
                        lid = inp.get_attribute("id")
                        if lid:
                            label_el = page.query_selector(f"label[for='{lid}']")
                            if label_el:
                                label_text = label_el.inner_text().lower()
                    except Exception:
                        pass

                    # Auto-fill known fields
                    val = ""
                    if "phone" in label_text or "mobile" in label_text:
                        val = profile.get("phone", "")
                    elif "email" in label_text:
                        val = profile.get("email", os.getenv("LINKEDIN_EMAIL", ""))
                    elif "city" in label_text or "location" in label_text:
                        val = profile.get("location", "")
                    elif "linkedin" in label_text:
                        val = profile.get("linkedin_url", "")
                    elif "website" in label_text or "portfolio" in label_text:
                        val = profile.get("website", "")

                    if val:
                        try:
                            inp.fill(val)
                        except Exception:
                            pass

                # Fill cover letter textarea if present
                if cover_letter:
                    textareas = page.query_selector_all("textarea")
                    for ta in textareas:
                        try:
                            placeholder = (ta.get_attribute("placeholder") or "").lower()
                            if any(kw in placeholder for kw in ("cover", "letter", "tell us", "message")):
                                ta.fill(cover_letter[:2000])
                                break
                        except Exception:
                            pass

                steps_completed += 1

                # Check for Next / Review / Submit
                next_btn   = page.query_selector('button[aria-label="Continue to next step"]')
                review_btn = page.query_selector('button[aria-label="Review your application"]')
                submit_btn = page.query_selector('button[aria-label="Submit application"]')

                if submit_btn:
                    if dry_run:
                        return {
                            "success": True,
                            "steps_completed": steps_completed,
                            "message": "DRY RUN: Reached Submit — application NOT sent. Toggle off dry_run to submit.",
                        }
                    submit_btn.click()
                    time.sleep(2)
                    return {
                        "success": True,
                        "steps_completed": steps_completed,
                        "message": "Application submitted.",
                    }
                elif review_btn:
                    review_btn.click()
                    time.sleep(1)
                elif next_btn:
                    next_btn.click()
                    time.sleep(1)
                else:
                    break

            return {
                "success": False,
                "steps_completed": steps_completed,
                "message": "Could not complete form — manual action required.",
            }

        except Exception as e:
            return {"success": False, "steps_completed": 0, "message": str(e)}


# ── High-level runner ──────────────────────────────────────────────

def run_apply_session(
    role: str,
    location: str,
    profile: dict,
    resume_text: str,
    confirm_callback,
    status_callback=None,
    max_per_session: int = _MAX_PER_SESSION,
    dry_run: bool = True,
    experience_filter: str = "",
) -> Generator[dict, None, None]:
    """
    Full agentic apply session.

    For each job found:
    1. Fetch job description
    2. Score resume vs JD
    3. Generate cover letter with Claude
    4. Call confirm_callback(job, score, cover_letter) → bool (user approves/skips)
    5. If approved: submit application (or dry_run)
    6. Log result + enforce delay

    Yields progress dicts: {job, score, status, cover_letter, result}
    confirm_callback must be synchronous (called from main thread).
    """
    from scorer import score_job
    from claude_ai import generate_cover_letter_claude

    applied_count = 0
    filters = {}
    if experience_filter:
        filters["experience"] = experience_filter

    def _cb(msg):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    with LinkedInSession() as session:
        _cb("Logging in to LinkedIn…")
        if not session.login():
            yield {"error": "LinkedIn login failed — check credentials in .env"}
            return

        _cb(f"Searching Easy Apply jobs for '{role}' in '{location}'…")
        jobs = session.search_easy_apply_jobs(
            role=role, location=location, filters=filters, max_results=80
        )
        _cb(f"Found {len(jobs)} Easy Apply jobs. Scoring against resume…")

        # Sort by score descending
        for job in jobs:
            try:
                jd = session.get_job_description(job["url"])
                job["description"] = jd
                job["score"] = score_job(resume_text, jd, job["title"])
            except Exception:
                job["score"] = 0
                job["description"] = ""

        jobs.sort(key=lambda j: j.get("score", 0), reverse=True)

        for job in jobs:
            if applied_count >= max_per_session:
                _cb(f"Session cap reached ({max_per_session} applications). Done.")
                break

            score = job.get("score", 0)
            if score < 30:
                continue  # skip poor matches silently

            # Generate cover letter
            _cb(f"Writing cover letter for {job['title']} @ {job['company']}…")
            profile_for_cl = {**profile, "raw_text": resume_text}
            cl = generate_cover_letter_claude(profile_for_cl, job) or ""

            # Human confirmation
            approved = confirm_callback(job, score, cl)
            if not approved:
                yield {
                    "job": job, "score": score, "status": "skipped",
                    "cover_letter": cl, "result": None,
                }
                continue

            _cb(f"Applying to {job['title']} @ {job['company']}…")
            result = session.apply_to_job(job, profile, cover_letter=cl, dry_run=dry_run)

            applied_count += 1
            yield {
                "job":          job,
                "score":        score,
                "status":       "applied" if result.get("success") else "failed",
                "cover_letter": cl,
                "result":       result,
            }

            if result.get("success") and not dry_run:
                _cb(f"Applied ({applied_count}/{max_per_session}). Waiting {_MIN_DELAY_SEC}s…")
                time.sleep(_MIN_DELAY_SEC)
            else:
                time.sleep(3)
