"""
market_intel.py
---------------
Free market intelligence — no API keys needed.

Sources:
  1. HackerNews "Ask HN: Who is Hiring?" via Algolia + Firebase APIs
  2. GitHub trending repos via GitHub Search API
  3. Jobicy aggregate skill counts from live job listings
"""

import os
import re
import json
import time
import requests
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from resume_parser import COMMON_SKILLS

_CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "market_intel_cache.json")
_CACHE_TTL  = 4 * 3600  # 4 hours

_HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"
_HN_FIREBASE = "https://hacker-news.firebaseio.com/v1/item"
_GH_SEARCH = "https://api.github.com/search/repositories"

# Extra tech terms beyond COMMON_SKILLS worth tracking
EXTRA_TERMS = [
    "ai", "llm", "gpt", "machine learning", "ml", "nlp", "data science",
    "blockchain", "web3", "solidity", "rust", "golang", "wasm",
    "next.js", "remix", "svelte", "tailwind", "vercel", "supabase",
    "openai", "langchain", "vector db", "rag", "fine-tuning",
    "product manager", "growth", "fintech", "saas", "b2b",
    "series a", "startup", "remote", "hybrid",
]

ALL_TERMS = [t for t in dict.fromkeys(COMMON_SKILLS + EXTRA_TERMS) if t.strip()]  # deduplicated, no empties


# ── HackerNews ──────────────────────────────────────────────────

def get_hn_hiring_thread():
    """Return (story_id, title) for the most recent 'Who is Hiring?' post."""
    try:
        r = requests.get(_HN_ALGOLIA, params={
            "query": "Ask HN: Who is Hiring",
            "tags": "story",
            "hitsPerPage": 1,
        }, timeout=10)
        hits = r.json().get("hits", [])
        if hits:
            return hits[0].get("objectID"), hits[0].get("title", "")
    except Exception:
        pass
    return None, None


def _fetch_comment(kid_id):
    try:
        r = requests.get(f"{_HN_FIREBASE}/{kid_id}.json", timeout=5)
        data = r.json()
        return data.get("text", "") if data else ""
    except Exception:
        return ""


def get_hn_comments(story_id, max_comments=60):
    """Fetch top-level comments from a HN thread (parallel)."""
    try:
        r = requests.get(f"{_HN_FIREBASE}/{story_id}.json", timeout=10)
        kids = (r.json().get("kids") or [])[:max_comments]
    except Exception:
        return []

    texts = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_comment, kid): kid for kid in kids}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                texts.append(result)
    return texts


@lru_cache(maxsize=64)
def _term_pattern(term):
    """Compile a word-boundary regex for a skill term (cached per term)."""
    return re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)


def count_terms(texts):
    """Count ALL_TERMS across a list of strings using word boundaries. Returns sorted (term, count)."""
    combined = " ".join(texts)
    counts = {}
    for term in ALL_TERMS:
        c = len(_term_pattern(term).findall(combined))
        if c > 0:
            counts[term] = c
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)


# ── GitHub ───────────────────────────────────────────────────────

def get_github_trending(days=30):
    """Repos with most new stars in the last N days (GitHub Search API)."""
    from datetime import datetime as _dt, timedelta
    since = (_dt.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    gh_token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"
    try:
        r = requests.get(_GH_SEARCH, params={
            "q": f"created:>{since} stars:>100",
            "sort": "stars",
            "order": "desc",
            "per_page": 20,
        }, headers=headers, timeout=10)
        if r.status_code == 403:
            # Rate limited — return empty gracefully
            return []
        r.raise_for_status()
        items = r.json().get("items", [])
        repos = []
        for item in items:
            repos.append({
                "name": item["full_name"],
                "description": item.get("description") or "",
                "language": item.get("language") or "Unknown",
                "stars": item["stargazers_count"],
                "topics": item.get("topics", []),
                "url": item["html_url"],
            })
        return repos
    except Exception:
        return []


def count_languages(repos):
    langs = [r["language"] for r in repos if r["language"] != "Unknown"]
    return Counter(langs).most_common(12)


# ── Jobicy aggregate ────────────────────────────────────────────

def get_jobicy_skill_counts(roles=("software engineer", "data analyst", "product manager")):
    """Fetch a sample of Jobicy listings and count skill mentions."""
    all_text = []
    for role in roles:
        try:
            r = requests.get("https://jobicy.com/api/v2/remote-jobs",
                             params={"count": 20, "tag": role}, timeout=10)
            for job in r.json().get("jobs", []):
                desc = re.sub(r"<[^>]+>", " ", job.get("jobDescription", ""))
                all_text.append(desc)
        except Exception:
            continue
    return count_terms(all_text)


# ── Main entry ──────────────────────────────────────────────────

def get_market_intel():
    """
    Fetch all market intelligence in parallel.
    Returns dict with:
      hn_title, hn_skills, gh_repos, gh_languages, jobicy_skills

    Results are cached to disk for _CACHE_TTL seconds to avoid slow HN fetches on every load.
    """
    # ── Cache check ──────────────────────────────────────────────
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE) as f:
                cached = json.load(f)
            if time.time() - cached.get("_ts", 0) < _CACHE_TTL:
                cached.pop("_ts", None)
                return cached
        except Exception:
            pass

    results = {
        "hn_title": None,
        "hn_skills": [],
        "gh_repos": [],
        "gh_languages": [],
        "jobicy_skills": [],
    }

    def _hn():
        sid, title = get_hn_hiring_thread()
        if sid:
            texts = get_hn_comments(sid)
            return title, count_terms(texts)[:25]
        return None, []

    def _gh():
        repos = get_github_trending()
        return repos, count_languages(repos)

    def _jobicy():
        return get_jobicy_skill_counts()[:20]

    with ThreadPoolExecutor(max_workers=3) as pool:
        hn_fut = pool.submit(_hn)
        gh_fut = pool.submit(_gh)
        jc_fut = pool.submit(_jobicy)

        try:
            title, hn_skills = hn_fut.result(timeout=25)
        except Exception:
            title, hn_skills = None, []
        try:
            repos, langs = gh_fut.result(timeout=25)
        except Exception:
            repos, langs = [], []
        try:
            jc_skills = jc_fut.result(timeout=25)
        except Exception:
            jc_skills = []

    results["hn_title"] = title
    results["hn_skills"] = hn_skills
    results["gh_repos"] = repos[:12]
    results["gh_languages"] = langs
    results["jobicy_skills"] = jc_skills

    # ── Write cache ──────────────────────────────────────────────
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump({**results, "_ts": time.time()}, f)
    except Exception:
        pass

    return results
