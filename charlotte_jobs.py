"""
charlotte_jobs.py — Charlotte-specific job scraping (LinkedIn, employer pages, Workday ATS).
All functions return a list of job dicts matching the standard CareerIQ schema.
"""
import re
import hashlib
import requests
from datetime import datetime

_TIMEOUT = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _job_id(company: str, title: str) -> str:
    raw = f"{company.lower().strip()}_{title.lower().strip()}_charlotte"
    return "clt_" + hashlib.md5(raw.encode()).hexdigest()[:12]


# ── Indeed Charlotte Scrape ───────────────────────────────────────

def fetch_indeed_charlotte(keywords: list[str], max_results: int = 20) -> list[dict]:
    """Scrape Indeed for Charlotte design/creative jobs."""
    jobs = []
    seen: set[str] = set()

    for kw in keywords[:3]:
        try:
            import urllib.parse
            q   = urllib.parse.quote(kw)
            loc = urllib.parse.quote("Charlotte, NC")
            url = f"https://www.indeed.com/jobs?q={q}&l={loc}&sort=date&limit=15"
            r   = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue

            # Extract job cards
            cards = re.findall(
                r'<div[^>]*class="[^"]*job_seen_beacon[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                r.text, re.DOTALL
            )

            for card in cards:
                title_m   = re.search(r'<span[^>]*title="([^"]+)"', card)
                company_m = re.search(r'class="[^"]*companyName[^"]*"[^>]*>([^<]+)<', card)
                link_m    = re.search(r'href="(/rc/clk\?[^"]+|/pagead/clk\?[^"]+)"', card)
                desc_m    = re.search(r'class="[^"]*job-snippet[^"]*"[^>]*>(.*?)</ul>', card, re.DOTALL)

                title   = title_m.group(1).strip()   if title_m   else ""
                company = company_m.group(1).strip() if company_m else ""
                rel_url = link_m.group(1)             if link_m    else ""
                url_val = f"https://www.indeed.com{rel_url}" if rel_url else "https://www.indeed.com"
                desc    = re.sub(r"<[^>]+>", " ", desc_m.group(1)).strip() if desc_m else ""

                if not title or title in seen:
                    continue
                seen.add(title)

                jobs.append({
                    "id":          _job_id(company, title),
                    "title":       title,
                    "company":     company,
                    "location":    "Charlotte, NC",
                    "description": desc[:600],
                    "url":         url_val,
                    "source":      "Indeed",
                    "salary_min":  None,
                    "salary_max":  None,
                    "date":        datetime.now().isoformat()[:10],
                })

                if len(jobs) >= max_results:
                    return jobs

        except Exception:
            continue

    return jobs


# ── LinkedIn Public Job Search ────────────────────────────────────

def fetch_linkedin_charlotte(keywords: list[str], max_results: int = 20) -> list[dict]:
    """
    Fetch Charlotte jobs from LinkedIn public job search (no login required).
    Uses LinkedIn's public jobs API endpoint.
    """
    jobs = []
    seen = set()

    for kw in keywords[:3]:
        try:
            import urllib.parse
            q   = urllib.parse.quote(kw)
            loc = urllib.parse.quote("Charlotte, North Carolina, United States")
            url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={q}&location={loc}&start=0&count=10"
            )
            r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue

            # Parse job cards from response HTML
            cards = re.findall(r'<li[^>]*class="[^"]*result-card[^"]*"[^>]*>(.*?)</li>',
                               r.text, re.DOTALL)
            if not cards:
                # Try alternative structure
                cards = re.findall(r'<div[^>]*class="[^"]*job-search-card[^"]*"[^>]*>(.*?)</div>',
                                   r.text, re.DOTALL)

            for card in cards:
                title_m   = re.search(r'class="[^"]*job-title[^"]*"[^>]*>\s*(.*?)\s*<', card)
                company_m = re.search(r'class="[^"]*subtitle[^"]*"[^>]*>\s*(.*?)\s*<', card)
                link_m    = re.search(r'href="(https://www\.linkedin\.com/jobs/view/[^"]+)"', card)
                loc_m     = re.search(r'class="[^"]*location[^"]*"[^>]*>\s*(.*?)\s*<', card)

                title   = re.sub(r"<[^>]+>","",title_m.group(1)).strip()   if title_m   else ""
                company = re.sub(r"<[^>]+>","",company_m.group(1)).strip() if company_m else ""
                url_val = link_m.group(1).split("?")[0]                     if link_m    else ""
                loc     = re.sub(r"<[^>]+>","",loc_m.group(1)).strip()     if loc_m     else "Charlotte, NC"

                if not title or title in seen:
                    continue
                seen.add(title)

                jobs.append({
                    "id":          _job_id(company, title),
                    "title":       title,
                    "company":     company,
                    "location":    loc or "Charlotte, NC",
                    "description": f"{title} at {company} in Charlotte. Apply on LinkedIn.",
                    "url":         url_val,
                    "source":      "LinkedIn",
                    "salary_min":  None,
                    "salary_max":  None,
                    "date":        datetime.now().isoformat()[:10],
                })

                if len(jobs) >= max_results:
                    return jobs

        except Exception:
            continue

    return jobs


# ── Charlotte Employer Career Pages ──────────────────────────────

# Key Charlotte employers with in-house creative/design teams
CHARLOTTE_DESIGN_EMPLOYERS = [
    # Creative Staffing Agencies — Charlotte market
    {"company": "Creative Circle",        "careers_url": "https://www.creativecircle.com/find-work/?q=designer&l=charlotte+nc", "search_term": "designer"},
    {"company": "Vitamin T",              "careers_url": "https://vitamintalent.com/find-talent/", "search_term": "design"},
    {"company": "24 Seven Talent",        "careers_url": "https://www.24seventalent.com/find-work/?q=graphic+designer&location=Charlotte", "search_term": "designer"},
    {"company": "Artisan Creative",       "careers_url": "https://artisancreative.com/find-work/", "search_term": "design"},
    # Agencies
    {"company": "BooneOakley",            "careers_url": "https://booneoakley.com/careers", "search_term": "designer"},
    {"company": "Wray Ward",              "careers_url": "https://www.wrayward.com/careers", "search_term": "designer"},
    {"company": "Idea Creative",          "careers_url": "https://ideacreative.com/careers/", "search_term": "design"},
    # Corp in-house
    {"company": "Red Ventures",           "careers_url": "https://www.redventures.com/careers", "search_term": "design"},
    {"company": "Ally Financial",         "careers_url": "https://www.ally.com/about/careers/", "search_term": "design"},
    {"company": "Lowe's",                 "careers_url": "https://talent.lowes.com/us/en/search-results", "search_term": "graphic design"},
    {"company": "Bank of America",        "careers_url": "https://careers.bankofamerica.com/", "search_term": "graphic designer"},
    {"company": "Atrium Health",          "careers_url": "https://careers.atriumhealth.org/", "search_term": "graphic design"},
    {"company": "Duke Energy",            "careers_url": "https://careers.duke-energy.com/", "search_term": "graphic design"},
    {"company": "Honeywell",              "careers_url": "https://careers.honeywell.com/", "search_term": "graphic designer"},
    {"company": "Synchrony",              "careers_url": "https://www.synchrony.com/careers", "search_term": "designer"},
    {"company": "LendingTree",            "careers_url": "https://www.lendingtree.com/careers/", "search_term": "designer"},
    {"company": "Novant Health",          "careers_url": "https://www.novanthealth.org/careers", "search_term": "graphic design"},
    {"company": "Charlotte Hornets",      "careers_url": "https://www.nba.com/hornets/jobs", "search_term": "design"},
    {"company": "Panthers",               "careers_url": "https://www.panthers.com/team/front-office/jobs/", "search_term": "design"},
]


def fetch_charlotte_employers(max_per_employer: int = 3) -> list[dict]:
    """
    Check Charlotte employer career pages for design openings.
    Uses lightweight text matching — not full scraping.
    Returns job placeholders pointing to the careers page.
    """
    jobs = []
    design_keywords = [
        "graphic design", "visual design", "digital design", "creative",
        "designer", "illustrat", "brand", "motion", "multimedia",
    ]

    for emp in CHARLOTTE_DESIGN_EMPLOYERS:
        try:
            r = requests.get(emp["careers_url"], headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue
            text_lower = re.sub(r"<[^>]+>", " ", r.text).lower()

            # Look for design-related job postings on the page
            found_any = any(kw in text_lower for kw in design_keywords)
            if not found_any:
                continue

            # Find job titles near design keywords
            # Look for common patterns like "Graphic Designer", "Creative Director", etc.
            title_patterns = re.findall(
                r"((?:graphic|visual|digital|brand|motion|senior|junior|lead|creative|ux|ui)"
                r"\s+(?:design(?:er)?|director|coordinator|specialist|manager|artist))",
                text_lower,
            )
            titles_found = list(set(t.title() for t in title_patterns[:max_per_employer]))

            if not titles_found:
                # Generic placeholder if keywords found but no specific title
                titles_found = [f"Design Role — {emp['company']}"]

            for title in titles_found[:max_per_employer]:
                jobs.append({
                    "id":          _job_id(emp["company"], title),
                    "title":       title,
                    "company":     emp["company"],
                    "location":    "Charlotte, NC",
                    "description": (
                        f"{emp['company']} is hiring for design roles in Charlotte. "
                        f"Visit their careers page to see current openings and apply directly."
                    ),
                    "url":         emp["careers_url"],
                    "source":      "Direct",
                    "salary_min":  None,
                    "salary_max":  None,
                    "date":        datetime.now().isoformat()[:10],
                })

        except Exception:
            continue

    return jobs


# ── Workday ATS Scrapers ─────────────────────────────────────────

WORKDAY_EMPLOYERS = [
    {"company": "Lowe's",         "tenant": "lowes",        "num": 5, "board": "Lowes"},
    {"company": "Duke Energy",    "tenant": "energyjobs",   "num": 5, "board": "DukeEnergy"},
    {"company": "Atrium Health",  "tenant": "atriumhealth", "num": 1, "board": "External"},
    {"company": "Honeywell",      "tenant": "honeywell",    "num": 5, "board": "Honeywell"},
    {"company": "Bank of America","tenant": "bofa",         "num": 5, "board": "Global"},
]


def _fetch_workday(tenant: str, num: int, board: str, query: str,
                   company: str, max_results: int = 5) -> list[dict]:
    """
    Fetch jobs from a Workday career page via their JSON API.
    POST https://{tenant}.wd{num}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs
    """
    from datetime import timedelta
    url = f"https://{tenant}.wd{num}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"
    base_job_url = f"https://{tenant}.wd{num}.myworkdayjobs.com/en-US/{board}"
    try:
        r = requests.post(
            url,
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": query},
            headers={**_HEADERS, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for jp in r.json().get("jobPostings", [])[:max_results]:
            title       = jp.get("title", "").strip()
            ext_path    = jp.get("externalPath", "")
            location    = jp.get("locationsText", "Charlotte, NC")
            posted_on   = jp.get("postedOn", "")
            # Parse "Posted X Days Ago" → estimate date
            job_date = datetime.now().isoformat()[:10]
            m = re.search(r"(\d+)\s+day", posted_on, re.IGNORECASE)
            if m:
                days_ago = int(m.group(1))
                job_date = (datetime.now() - timedelta(days=days_ago)).isoformat()[:10]
            if not title:
                continue
            jobs.append({
                "id":          _job_id(company, title),
                "title":       title,
                "company":     company,
                "location":    location or "Charlotte, NC",
                "description": (
                    f"{title} at {company}. Apply via {company}'s Workday career portal."
                ),
                "url":         f"{base_job_url}{ext_path}" if ext_path else base_job_url,
                "source":      "Workday",
                "salary_min":  None,
                "salary_max":  None,
                "date":        job_date,
            })
        return jobs
    except Exception:
        return []


def fetch_charlotte_workday(keywords: list[str], max_per_employer: int = 5) -> list[dict]:
    """Fetch design/creative jobs from major Charlotte employers' Workday ATS pages."""
    jobs = []
    seen = set()

    for emp in WORKDAY_EMPLOYERS:
        for kw in keywords[:3]:
            for j in _fetch_workday(
                emp["tenant"], emp["num"], emp["board"], kw,
                emp["company"], max_per_employer
            ):
                key = f"{j['title'].lower()}_{j['company'].lower()}"
                if key not in seen:
                    seen.add(key)
                    jobs.append(j)

    return jobs


# ── Combined Charlotte Search ─────────────────────────────────────

def fetch_all_charlotte_design_jobs(target_roles: list[str] | None = None) -> list[dict]:
    """
    Master function — pulls from Indeed, LinkedIn, and direct employer pages.
    Deduplicates by title+company.
    """
    keywords = target_roles or [
        "graphic designer", "digital designer", "visual designer",
        "brand designer", "marketing designer",
    ]

    all_jobs = []
    seen = set()

    # Indeed — best coverage of local jobs
    indeed_jobs = fetch_indeed_charlotte(keywords, max_results=25)
    for j in indeed_jobs:
        key = f"{j['title'].lower()}_{j['company'].lower()}"
        if key not in seen:
            seen.add(key)
            all_jobs.append(j)

    # LinkedIn public
    li_jobs = fetch_linkedin_charlotte(keywords[:2], max_results=15)
    for j in li_jobs:
        key = f"{j['title'].lower()}_{j['company'].lower()}"
        if key not in seen:
            seen.add(key)
            all_jobs.append(j)

    # Charlotte employer career pages (HTML scraping)
    employer_jobs = fetch_charlotte_employers()
    for j in employer_jobs:
        key = f"{j['title'].lower()}_{j['company'].lower()}"
        if key not in seen:
            seen.add(key)
            all_jobs.append(j)

    # Workday ATS — freshest data, direct from employer ATS
    workday_jobs = fetch_charlotte_workday(keywords)
    for j in workday_jobs:
        key = f"{j['title'].lower()}_{j['company'].lower()}"
        if key not in seen:
            seen.add(key)
            all_jobs.append(j)

    return all_jobs


if __name__ == "__main__":
    print("Searching Charlotte design jobs...")
    jobs = fetch_all_charlotte_design_jobs()
    print(f"\nFound {len(jobs)} jobs:\n")
    for j in jobs:
        print(f"  [{j['source']:8s}] {j['title'][:40]:40s} @ {j['company'][:25]:25s}  {j['url'][:50]}")
