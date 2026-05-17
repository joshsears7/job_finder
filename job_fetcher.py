import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Fetch warnings ────────────────────────────────────────────────
# Each fetch function appends (source, reason) on failure so callers
# can surface "X source unavailable" messages instead of silent empty results.
_fetch_warnings: list[tuple[str, str]] = []


def get_fetch_warnings() -> list[tuple[str, str]]:
    """Return and clear accumulated fetch warnings: [(source, reason), ...]"""
    global _fetch_warnings
    w = list(_fetch_warnings)
    _fetch_warnings = []
    return w


def _warn(source: str, reason: str):
    _fetch_warnings.append((source, reason))


def _index_jobs_async(jobs: list) -> None:
    """Index fetched jobs into ChromaDB in a background thread. Never raises."""
    if not jobs:
        return
    def _do():
        try:
            from vector_store import index_job
            for j in jobs:
                if j.get("description", "").strip():
                    index_job(
                        job_id=str(j["id"]),
                        title=j.get("title", ""),
                        company=j.get("company", ""),
                        description=j.get("description", ""),
                        source=j.get("source", ""),
                        location=j.get("location", ""),
                    )
        except Exception:
            pass
    import threading
    threading.Thread(target=_do, daemon=True).start()


def _dedup_jobs(jobs: list[dict]) -> list[dict]:
    """
    Remove near-duplicate jobs across sources.
    Two jobs are duplicates if company + title are both highly similar.
    Keeps whichever version has richer data (salary preferred).
    """
    from difflib import SequenceMatcher

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    def _sim(a: str, b: str) -> float:
        na, nb = _norm(a), _norm(b)
        if not na or not nb:
            return 0.0
        return SequenceMatcher(None, na, nb).ratio()

    kept: list[dict] = []
    for job in jobs:
        is_dup = False
        for i, existing in enumerate(kept):
            co_sim    = _sim(existing.get("company", ""), job.get("company", ""))
            title_sim = _sim(existing.get("title",   ""), job.get("title",   ""))
            if co_sim >= 0.80 and title_sim >= 0.75:
                # Keep whichever has salary data; otherwise keep first seen
                if job.get("salary_min") and not existing.get("salary_min"):
                    kept[i] = job
                is_dup = True
                break
        if not is_dup:
            kept.append(job)
    return kept


ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

# City presets → Adzuna country code + display label
CITY_PRESETS = {
    # ── Domestic ──────────────────────────────────────────────
    "🗽 New York":        {"where": "New York",       "country": "us", "flag": "🇺🇸"},
    "🌲 Raleigh":         {"where": "Raleigh",        "country": "us", "flag": "🇺🇸"},
    "🏙️ Charlotte":      {"where": "Charlotte",      "country": "us", "flag": "🇺🇸"},
    "🏛️ Washington DC":  {"where": "Washington DC",  "country": "us", "flag": "🇺🇸"},
    "🏙️ Chicago":        {"where": "Chicago",        "country": "us", "flag": "🇺🇸"},
    "🌴 Los Angeles":     {"where": "Los Angeles",    "country": "us", "flag": "🇺🇸"},
    "🌉 San Francisco":   {"where": "San Francisco",  "country": "us", "flag": "🇺🇸"},
    "🌞 Miami":           {"where": "Miami",          "country": "us", "flag": "🇺🇸"},
    "🏔️ Atlanta":        {"where": "Atlanta",        "country": "us", "flag": "🇺🇸"},
    "🤠 Dallas":          {"where": "Dallas",         "country": "us", "flag": "🇺🇸"},
    "🚀 Houston":         {"where": "Houston",        "country": "us", "flag": "🇺🇸"},
    "🐟 Seattle":         {"where": "Seattle",        "country": "us", "flag": "🇺🇸"},
    "🦞 Boston":          {"where": "Boston",         "country": "us", "flag": "🇺🇸"},
    "🏔️ Denver":         {"where": "Denver",         "country": "us", "flag": "🇺🇸"},
    "🎵 Nashville":       {"where": "Nashville",      "country": "us", "flag": "🇺🇸"},
    "🌍 Remote":          {"where": "",               "country": "us", "flag": "🌍"},
    # ── International ─────────────────────────────────────────
    "🇬🇧 London":        {"where": "London",         "country": "gb", "flag": "🇬🇧"},
    "🇳🇱 Amsterdam":     {"where": "Amsterdam",      "country": "nl", "flag": "🇳🇱"},
    "🇮🇹 Milan":         {"where": "Milan",          "country": "it", "flag": "🇮🇹"},
    "🇩🇪 Berlin":        {"where": "Berlin",         "country": "de", "flag": "🇩🇪"},
    "🇫🇷 Paris":         {"where": "Paris",          "country": "fr", "flag": "🇫🇷"},
    "🇨🇦 Toronto":       {"where": "Toronto",        "country": "ca", "flag": "🇨🇦"},
    "🇮🇪 Dublin":        {"where": "Dublin",         "country": "ie", "flag": "🇮🇪"},
    "🇨🇭 Zurich":        {"where": "Zurich",         "country": "ch", "flag": "🇨🇭"},
    "🇸🇪 Stockholm":     {"where": "Stockholm",      "country": "se", "flag": "🇸🇪"},
    "🇪🇸 Barcelona":     {"where": "Barcelona",      "country": "es", "flag": "🇪🇸"},
}


def _strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ── Adzuna ───────────────────────────────────────────────────────

def fetch_adzuna(role, where="", country="us", num_results=20):
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": role,
        "results_per_page": num_results,
    }
    if where:
        params["where"] = where
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        jobs = []
        for j in r.json().get("results", []):
            jobs.append({
                "id": f"az_{j.get('id', '')}",
                "title": j.get("title", ""),
                "company": j.get("company", {}).get("display_name", "Unknown"),
                "location": j.get("location", {}).get("display_name", where or country.upper()),
                "salary_min": j.get("salary_min"),
                "salary_max": j.get("salary_max"),
                "description": j.get("description", ""),
                "url": j.get("redirect_url", ""),
                "source": "Adzuna",
                "date": (j.get("created") or "")[:10],
                "country": country,
            })
        return jobs
    except Exception as e:
        _warn("Adzuna", str(e))
        return []


# ── Jobicy ───────────────────────────────────────────────────────

_JOBICY_GEO = {
    "us": "USA", "gb": "UK", "nl": "Netherlands",
    "it": "Italy", "de": "Germany", "fr": "France",
}


def fetch_jobicy(role, country="", num_results=20):
    url = "https://jobicy.com/api/v2/remote-jobs"
    params = {"count": min(num_results, 50), "tag": role}
    geo = _JOBICY_GEO.get(country, "")
    if geo:
        params["geo"] = geo
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        jobs = []
        for j in r.json().get("jobs", [])[:num_results]:
            desc = _strip_html(j.get("jobDescription", j.get("jobExcerpt", "")))
            jobs.append({
                "id": f"jc_{j.get('id', '')}",
                "title": j.get("jobTitle", ""),
                "company": j.get("companyName", "Unknown"),
                "location": j.get("jobGeo") or "Remote",
                "salary_min": None,
                "salary_max": None,
                "description": desc,
                "url": j.get("url", ""),
                "source": "Jobicy",
                "date": (j.get("pubDate") or "")[:10],
                "country": country,
            })
        return jobs
    except Exception as e:
        _warn("Jobicy", str(e))
        return []


# ── The Muse ─────────────────────────────────────────────────────

def fetch_muse(role, num_results=15):
    url = "https://www.themuse.com/api/public/jobs"
    keywords = [w.lower() for w in role.split() if len(w) > 2]
    collected = []

    for page in range(6):
        if len(collected) >= num_results * 4:
            break
        try:
            r = requests.get(url, params={"page": page, "descending": "true"}, timeout=10)
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results:
                break
            collected.extend(results)
        except Exception:
            break

    jobs = []
    for j in collected:
        title = j.get("name", "").lower()
        desc = _strip_html(j.get("contents", ""))
        # Require all keywords in title OR all keywords in description (strict match)
        title_match = not keywords or all(kw in title for kw in keywords)
        desc_match  = not keywords or all(kw in desc.lower() for kw in keywords)
        if not (title_match or desc_match):
            continue
        locs = j.get("locations", [])
        loc = locs[0].get("name", "Remote") if locs else "Remote"
        jobs.append({
            "id": f"mu_{j.get('id', '')}",
            "title": j.get("name", ""),
            "company": j.get("company", {}).get("name", "Unknown"),
            "location": loc,
            "salary_min": None,
            "salary_max": None,
            "description": desc,
            "url": j.get("refs", {}).get("landing_page", ""),
            "source": "The Muse",
            "date": (j.get("publication_date") or "")[:10],
            "country": "us",
        })
        if len(jobs) >= num_results:
            break
    return jobs


# ── Remotive ─────────────────────────────────────────────────────

_REMOTIVE_CATEGORY = {
    "software": "software-dev", "engineer": "software-dev", "developer": "software-dev",
    "data": "data", "analyst": "data", "scientist": "data",
    "product": "product", "design": "design", "ux": "design",
    "marketing": "marketing", "sales": "sales", "finance": "finance",
    "hr": "human-resources", "recruiter": "human-resources",
    "devops": "devops-sysadmin", "security": "cybersecurity",
    "management": "management-finance", "project": "project-management",
}


def fetch_remotive(role, num_results=15):
    """Remote jobs from Remotive — free, no API key required."""
    role_lower = role.lower()
    category = next((v for k, v in _REMOTIVE_CATEGORY.items() if k in role_lower), "")
    try:
        params = {"limit": 20}
        if category:
            params["category"] = category
        else:
            params["search"] = role
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            params=params,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        jobs = []
        for j in r.json().get("jobs", [])[:num_results]:
            desc = _strip_html(j.get("description", ""))
            sal_min, sal_max = None, None
            sal_str = j.get("salary", "") or ""
            # Capture K suffix explicitly so "$500K" → 500,000 (not 500)
            m = re.search(r"\$?([\d,]+)([kK])?\s*[-–]\s*\$?([\d,]+)([kK])?", sal_str)
            if m:
                lo    = float(m.group(1).replace(",", ""))
                hi    = float(m.group(3).replace(",", ""))
                lo_k  = bool(m.group(2))
                hi_k  = bool(m.group(4))
                sal_min = lo * 1000 if (lo_k or lo < 500) else lo
                sal_max = hi * 1000 if (hi_k or hi < 500) else hi
            jobs.append({
                "id":          f"rm_{j.get('id', '')}",
                "title":       j.get("title", ""),
                "company":     j.get("company_name", "Unknown"),
                "location":    j.get("candidate_required_location") or "Remote",
                "salary_min":  sal_min,
                "salary_max":  sal_max,
                "description": desc[:2000],
                "url":         j.get("url", ""),
                "source":      "Remotive",
                "date":        (j.get("publication_date") or "")[:10],
                "country":     "us",
            })
        return jobs
    except Exception as e:
        _warn("Remotive", str(e))
        return []


# ── Arbeitnow ─────────────────────────────────────────────────────

def fetch_arbeitnow(role, num_results=15):
    """European & remote jobs from Arbeitnow — free, no API key required."""
    try:
        r = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        jobs = []
        # API ignores search param — filter client-side across title + tags
        kw = [w for w in role.lower().split() if len(w) > 2]
        for j in r.json().get("data", []):
            title = j.get("title", "").lower()
            tags  = " ".join(j.get("tags", [])).lower()
            desc  = _strip_html(j.get("description", "")).lower()
            combined = title + " " + tags
            if kw:
                # Require all keywords in title+tags OR at least 2 in description
                title_ok = all(k in combined for k in kw)
                desc_hits = sum(1 for k in kw if k in desc)
                if not title_ok and desc_hits < max(2, len(kw) // 2):
                    continue
            desc = _strip_html(j.get("description", ""))
            loc = j.get("location", "Remote")
            if j.get("remote"):
                loc = "Remote" if loc == "" else f"{loc} / Remote"
            jobs.append({
                "id":          f"an_{j.get('slug', j.get('title','')[:20])}",
                "title":       j.get("title", ""),
                "company":     j.get("company_name", "Unknown"),
                "location":    loc,
                "salary_min":  None,
                "salary_max":  None,
                "description": desc[:2000],
                "url":         j.get("url", ""),
                "source":      "Arbeitnow",
                "date":        str(j.get("created_at") or "")[:10],
                "country":     "eu",
            })
            if len(jobs) >= num_results:
                break
        return jobs
    except Exception as e:
        _warn("Arbeitnow", str(e))
        return []


# ── JSearch (RapidAPI) ──────────────────────────────────────────

def fetch_jsearch(role: str, location: str = "", num_results: int = 15) -> list[dict]:
    """
    JSearch API via RapidAPI — aggregates Indeed, LinkedIn, Glassdoor, and more.
    Requires JSEARCH_API_KEY in .env (free tier: 100 req/month).
    """
    key = os.getenv("JSEARCH_API_KEY", "")
    if not key:
        return []
    query = f"{role} in {location}" if location else role
    try:
        r = requests.get(
            "https://jsearch.p.rapidapi.com/search",
            headers={
                "X-RapidAPI-Key":  key,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            },
            params={"query": query, "page": "1", "num_pages": "1"},
            timeout=12,
        )
        r.raise_for_status()
        jobs = []
        for j in r.json().get("data", [])[:num_results]:
            sal_min = j.get("job_min_salary")
            sal_max = j.get("job_max_salary")
            # Convert hourly → annual
            if sal_min and str(j.get("job_salary_period", "")).lower() == "hour":
                sal_min = sal_min * 2080
                sal_max = (sal_max or sal_min) * 2080
            loc_parts = filter(None, [j.get("job_city"), j.get("job_state")])
            jobs.append({
                "id":          f"js_{j.get('job_id', '')}",
                "title":       j.get("job_title", ""),
                "company":     j.get("employer_name", "Unknown"),
                "location":    ", ".join(loc_parts) or location or "Unknown",
                "salary_min":  sal_min,
                "salary_max":  sal_max,
                "description": (j.get("job_description") or "")[:2000],
                "url":         j.get("job_apply_link") or j.get("job_google_link") or "",
                "source":      "JSearch",
                "date":        (j.get("job_posted_at_datetime_utc") or "")[:10],
                "country":     "us",
            })
        return jobs
    except Exception as e:
        _warn("JSearch", str(e))
        return []


# ── Multi-city search ────────────────────────────────────────────

def fetch_jobs_multicity(role, selected_cities, num_per_city=10):
    """
    Fetch jobs across multiple city presets.
    selected_cities: list of keys from CITY_PRESETS, e.g. ["🗽 New York", "🇬🇧 London"]
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_jobs = []
    seen_ids = set()

    def _fetch_city(city_key):
        info = CITY_PRESETS[city_key]
        jobs = []
        jobs += fetch_adzuna(role, info["where"], info["country"], num_per_city)
        if not jobs:  # fallback to Jobicy/Muse if no Adzuna key
            jobs += fetch_jobicy(role, info["country"], num_per_city)
        # Tag each job with the city label
        for j in jobs:
            j["city_label"] = city_key
        return jobs

    if "🌍 Remote" in selected_cities:
        remote_jobs = []
        remote_jobs += fetch_jobicy(role, "", num_per_city)
        remote_jobs += fetch_muse(role, num_per_city)
        remote_jobs += fetch_remotive(role, num_per_city)
        for j in remote_jobs:
            j["city_label"] = "🌍 Remote"
        all_jobs += remote_jobs

    if "🏙️ Charlotte" in selected_cities:
        try:
            from charlotte_jobs import fetch_all_charlotte_design_jobs
            clt_jobs = fetch_all_charlotte_design_jobs(target_roles=[role])
            for j in clt_jobs:
                j["city_label"] = "🏙️ Charlotte"
            all_jobs += clt_jobs
        except Exception as e:
            _warn("Charlotte", str(e))

    non_remote = [c for c in selected_cities if c != "🌍 Remote"]
    if non_remote:
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_fetch_city, c): c for c in non_remote}
            for fut in as_completed(futures):
                all_jobs += fut.result()

    # Deduplicate by id first, then by fuzzy title+company
    unique = []
    for j in all_jobs:
        if j["id"] not in seen_ids:
            seen_ids.add(j["id"])
            unique.append(j)

    result = _dedup_jobs(unique)
    _index_jobs_async(result)
    return result


def fetch_jobs(role, location="", num_results=20):
    """Single-location search — hits all available sources."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    jobs = []
    seen_ids = set()

    def _add(fetched):
        for j in fetched:
            if j["id"] not in seen_ids:
                seen_ids.add(j["id"])
                jobs.append(j)

    if ADZUNA_APP_ID and ADZUNA_APP_KEY:
        _add(fetch_adzuna(role, location, "us", num_results))

    if "charlotte" in location.lower():
        try:
            from charlotte_jobs import fetch_all_charlotte_design_jobs
            _add(fetch_all_charlotte_design_jobs(target_roles=[role]))
        except Exception as e:
            _warn("Charlotte", str(e))

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [
            pool.submit(fetch_jobicy,    role, "",       12),
            pool.submit(fetch_muse,      role,           10),
            pool.submit(fetch_remotive,  role,           12),
            pool.submit(fetch_arbeitnow, role,           10),
            pool.submit(fetch_jsearch,   role, location, 10),
        ]
        for f in as_completed(futures):
            try:
                _add(f.result())
            except Exception:
                pass

    result = _dedup_jobs(jobs)
    _index_jobs_async(result)
    return result


def has_adzuna():
    return bool(ADZUNA_APP_ID and ADZUNA_APP_KEY)


def has_jsearch():
    return bool(os.getenv("JSEARCH_API_KEY"))
