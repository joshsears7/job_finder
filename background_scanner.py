#!/usr/bin/env python3
"""
background_scanner.py
---------------------
Silent background daemon that finds new jobs matching your profile,
scores them, auto-saves above your threshold, and fires macOS notifications.

Run via LaunchAgent (auto-installed with setup_scanner.py) or manually:
    python background_scanner.py          # one scan, then exit
    python background_scanner.py --watch  # loop every N hours per profile

Logs each run to scanner_runs table in SQLite.
"""

import os
import sys
import time
import subprocess
import argparse
import logging
from datetime import datetime

# Add app directory to path so we can import modules
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

_IS_CLOUD = bool(os.getenv("SPACE_ID") or os.getenv("RAILWAY_ENVIRONMENT"))
if _IS_CLOUD:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(asctime)s [SCANNER] %(message)s")
else:
    logging.basicConfig(
        filename=os.path.join(os.path.dirname(__file__), "scanner.log"),
        level=logging.INFO,
        format="%(asctime)s [SCANNER] %(message)s",
    )
log = logging.getLogger("scanner")


def send_notification(title: str, message: str, subtitle: str = ""):
    """Send a macOS notification via osascript. No-op on non-macOS or cloud environments."""
    if sys.platform != "darwin" or _IS_CLOUD:
        return
    try:
        script = (
            f'display notification "{message}" with title "{title}"'
            + (f' subtitle "{subtitle}"' if subtitle else "")
        )
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
    except Exception:
        pass


def _score_job_fast(resume_text: str, job_description: str, job_title: str,
                    target_roles: list | None = None) -> int:
    """
    Fast keyword-based scoring (no ML model load).
    Adapts keyword pool from target_roles so it works for any profession.
    Returns 0-100 score.
    """
    if not resume_text or not job_description:
        return 40

    resume_lower = resume_text.lower()
    jd_lower = (job_description + " " + job_title).lower()

    # Universal base keywords present in almost every professional role
    BASE_KEYWORDS = [
        "communication", "collaboration", "team", "leadership", "project",
        "management", "strategy", "analytics", "content", "social media",
        "presentation", "research", "digital", "brand", "marketing",
    ]

    # Role-specific keyword pools — auto-selected from target_roles
    ROLE_KEYWORD_MAP = {
        "design": [
            "graphic design", "visual design", "digital design", "brand design",
            "adobe", "photoshop", "illustrator", "indesign", "premiere",
            "figma", "sketch", "typography", "layout", "ui", "ux",
            "web design", "print", "motion", "creative", "portfolio",
            "branding", "identity", "illustration", "photography", "canva",
            "after effects", "color", "composition", "mockup", "wireframe",
        ],
        "marketing": [
            "marketing", "campaign", "seo", "sem", "email marketing", "hubspot",
            "salesforce", "crm", "google analytics", "paid media", "growth",
            "conversion", "copywriting", "content marketing", "social media",
            "influencer", "roi", "a/b testing", "market research",
        ],
        "business": [
            "business development", "sales", "revenue", "pipeline", "strategy",
            "operations", "consulting", "finance", "excel", "powerpoint",
            "international", "entrepreneurship", "startup", "growth", "bd",
        ],
        "tech": [
            "python", "sql", "javascript", "react", "node", "api", "aws",
            "data", "machine learning", "software", "engineering", "backend",
            "frontend", "devops", "cloud", "database",
        ],
        "communications": [
            "communications", "pr", "public relations", "media relations",
            "press release", "journalism", "writing", "editing", "storytelling",
            "crisis communications", "internal communications", "copywriting",
        ],
    }

    # Build keyword pool from target roles
    keywords = list(BASE_KEYWORDS)
    if target_roles:
        roles_str = " ".join(target_roles).lower()
        for pool_key, pool_kws in ROLE_KEYWORD_MAP.items():
            if pool_key in roles_str or any(pool_key in r.lower() for r in target_roles):
                keywords.extend(pool_kws)
    if not target_roles or len(keywords) <= len(BASE_KEYWORDS):
        # Fallback: include all pools
        for pool_kws in ROLE_KEYWORD_MAP.values():
            keywords.extend(pool_kws)

    keywords = list(set(keywords))

    resume_hits = [kw for kw in keywords if kw in resume_lower]
    jd_hits     = [kw for kw in keywords if kw in jd_lower]
    overlap     = set(resume_hits) & set(jd_hits)

    if not jd_hits:
        return 38
    match_rate = len(overlap) / max(len(jd_hits), 1)
    score = int(38 + match_rate * 52)

    # Title relevance gate — heavily penalize jobs whose title doesn't match any target role
    if target_roles:
        jt_lower = job_title.lower()
        # Extract meaningful words from target roles
        role_words = set()
        for r in target_roles:
            for w in r.lower().split():
                if len(w) > 3:
                    role_words.add(w)
        title_words = set(jt_lower.split())
        # If title shares NO words with any target role, it's irrelevant
        if not role_words & title_words:
            return max(0, score - 40)
        # If title directly contains a target role string, bonus
        if any(r.lower() in jt_lower or jt_lower in r.lower() for r in target_roles):
            score = min(100, score + 12)

    # Entry-level / new grad boost
    if any(w in jd_lower for w in ["entry level", "new grad", "recent grad",
                                    "junior", "associate", "0-2 years", "1-2 years"]):
        score = min(100, score + 8)

    return max(0, min(100, score))


def run_scan(user_id: int = 1) -> dict:
    """
    Run one full scan cycle for the given user.
    Returns summary dict: {jobs_found, jobs_saved, jobs_notified, duration}
    """
    start = time.time()
    log.info(f"Starting scan for user_id={user_id}")

    import profile_store
    import tracker
    from job_fetcher import fetch_jobs

    profile = profile_store.get_profile(user_id)
    resume_text = profile_store.get_resume_text(user_id)

    roles  = profile.get("target_roles", [])
    cities = profile.get("target_cities", [])
    threshold   = int(profile.get("auto_save_threshold", 60))
    fresh_thr   = int(profile.get("fresh_threshold", 72))
    notify_fresh = bool(profile.get("notify_on_fresh", True))
    blacklist   = [c.lower() for c in profile.get("blacklist_companies", [])]

    if not roles:
        log.info("No target roles configured — skipping scan")
        return {}

    # Build geography filter from profile
    target_countries = [c.lower() for c in profile.get("target_countries", [])]
    target_cities_lower = [c.lower() for c in cities]
    open_to_remote = bool(profile.get("open_to_remote", True))

    # US-only cities trigger a strict geography check
    _us_only = (
        target_cities_lower
        and all(c not in ("london","dublin","amsterdam","berlin","paris","toronto","stockholm","barcelona","milan","zurich","remote","") for c in target_cities_lower)
        and not any(c in target_countries for c in ["uk","ireland","netherlands","germany","france","canada"])
    )

    def _location_ok(job: dict) -> bool:
        """Return False if this job is clearly in the wrong geography."""
        loc = (job.get("location") or "").lower()
        src = (job.get("source") or "").lower()
        # Always allow remote if user is open to it
        if open_to_remote and any(w in loc for w in ["remote", "worldwide", "anywhere"]):
            return True
        # If we know user is US-only, reject clearly non-US locations
        if _us_only:
            non_us_signals = [
                "germany", "deutschland", "berlin", "munich", "hamburg", "frankfurt",
                "london", "uk", "amsterdam", "netherlands", "paris", "france",
                "toronto", "canada", "dublin", "ireland", "stockholm", "sweden",
                "barcelona", "spain", "milan", "italy", "zurich", "switzerland",
                "singapore", "australia", "india", "israel", "latam", "asia",
                "europe", "emea",
            ]
            if any(sig in loc for sig in non_us_signals):
                return False
        # If target cities specified, require at least one to appear in location
        if target_cities_lower and not open_to_remote:
            return any(c in loc for c in target_cities_lower)
        return True

    jobs_found = jobs_saved = jobs_notified = 0
    top_jobs = []

    # Scan a subset of cities per run (rotate to avoid API limits)
    scan_cities = cities[:6] if cities else [""]  # limit per run

    # Charlotte-only design users: run charlotte_jobs directly for richer local results
    is_charlotte_designer = (
        target_cities_lower == ["charlotte"]
        and any("design" in r.lower() or "creative" in r.lower() or "graphic" in r.lower() for r in roles)
    )
    if is_charlotte_designer:
        try:
            from charlotte_jobs import fetch_all_charlotte_design_jobs
            clt_jobs = fetch_all_charlotte_design_jobs(target_roles=roles[:5])
            jobs_found += len(clt_jobs)
            for j in clt_jobs:
                if tracker.is_saved(j["id"]):
                    continue
                company_lower = (j.get("company") or "").lower()
                if any(bl in company_lower for bl in blacklist):
                    continue
                score = _score_job_fast(resume_text, j.get("description", ""), j.get("title", ""), target_roles=roles)
                j["score"] = score
                if score >= threshold:
                    saved = tracker.save_job(j, score)
                    if saved:
                        jobs_saved += 1
                        log.info(f"Saved [Charlotte]: {j['title']} @ {j['company']} ({score}%)")
                        if score >= fresh_thr:
                            top_jobs.append(j)
                            jobs_notified += 1
        except Exception as e:
            log.warning(f"Charlotte jobs fetch error: {e}")

    for role in roles[:5]:  # limit roles per run
        for city in scan_cities[:3]:
            try:
                fetched = fetch_jobs(role, city, num_results=10)
                jobs_found += len(fetched)

                for j in fetched:
                    # Geography filter
                    if not _location_ok(j):
                        continue

                    company_lower = (j.get("company") or "").lower()
                    if any(bl in company_lower for bl in blacklist):
                        continue

                    # Skip if already saved
                    if tracker.is_saved(j["id"]):
                        continue

                    score = _score_job_fast(resume_text, j.get("description",""), j.get("title",""), target_roles=roles)
                    j["score"] = score

                    if score >= threshold:
                        saved = tracker.save_job(j, score)
                        if saved:
                            jobs_saved += 1
                            log.info(f"Saved: {j['title']} @ {j['company']} ({score}%)")

                            if score >= fresh_thr:
                                top_jobs.append(j)
                                jobs_notified += 1

            except Exception as e:
                log.warning(f"Fetch error for {role}/{city}: {e}")

    duration = round(time.time() - start, 1)

    # Send macOS notification
    if top_jobs and notify_fresh:
        best = sorted(top_jobs, key=lambda x: -x.get("score", 0))[:3]
        if len(best) == 1:
            j = best[0]
            send_notification(
                "CareerIQ — New Match",
                f"{j['title']} at {j['company']}",
                subtitle=f"{j.get('score',0)}% fit · {j.get('location','')}",
            )
        else:
            send_notification(
                "CareerIQ — New Matches",
                f"{len(best)} high-fit jobs found",
                subtitle=", ".join(j["company"] for j in best[:3]),
            )
    elif jobs_saved > 0:
        send_notification(
            "CareerIQ",
            f"{jobs_saved} new job(s) saved to your queue",
        )

    # Log run
    tracker.log_scanner_run(
        jobs_found=jobs_found,
        jobs_saved=jobs_saved,
        jobs_notified=jobs_notified,
        cities=", ".join(scan_cities),
        roles=", ".join(roles[:5]),
        duration=duration,
        user_id=user_id,
    )

    log.info(f"Scan complete — found={jobs_found} saved={jobs_saved} notified={jobs_notified} ({duration}s)")
    return {
        "jobs_found":    jobs_found,
        "jobs_saved":    jobs_saved,
        "jobs_notified": jobs_notified,
        "duration":      duration,
        "top_jobs":      top_jobs,
    }


def watch_loop(user_id: int = 1):
    """Run scan in a loop using the interval set in the user profile."""
    import profile_store
    profile = profile_store.get_profile(user_id)
    interval_hours = float(profile.get("scan_interval_hours", 4))
    interval_secs  = interval_hours * 3600
    log.info(f"Watch mode: scanning every {interval_hours}h")
    while True:
        try:
            run_scan(user_id)
        except Exception as e:
            log.error(f"Scan failed: {e}")
        time.sleep(interval_secs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CareerIQ background scanner")
    parser.add_argument("--watch",   action="store_true", help="Loop continuously")
    parser.add_argument("--user-id", type=int, default=1,  help="User ID to scan for")
    args = parser.parse_args()

    if args.watch:
        watch_loop(args.user_id)
    else:
        result = run_scan(args.user_id)
        print(f"Scan complete: {result.get('jobs_found',0)} found, "
              f"{result.get('jobs_saved',0)} saved, "
              f"{result.get('jobs_notified',0)} notified")
