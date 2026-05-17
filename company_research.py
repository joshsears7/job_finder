"""
company_research.py
-------------------
Agentic company intelligence: news, funding signals, tech stack, culture,
hiring velocity, and competitive context — all from free public sources.
Claude synthesizes the raw signals into a structured dossier.
"""

import os
import re
import time
import threading
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1 hour


def _cached(key: str, fn, *args, **kwargs):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < _CACHE_TTL:
            return entry["data"]
    result = fn(*args, **kwargs)
    with _cache_lock:
        _cache[key] = {"data": result, "ts": time.time()}
    return result


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ── News via GNews RSS ────────────────────────────────────────────

def fetch_company_news(company: str, max_articles: int = 8) -> list[dict]:
    """Pull recent news for a company via Google News RSS."""
    def _fetch():
        query = f'"{company}"'
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10)
            r.raise_for_status()
            items = re.findall(r"<item>(.*?)</item>", r.text, re.DOTALL)
            articles = []
            for item in items[:max_articles]:
                title = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item)
                link  = re.search(r"<link>(.*?)</link>", item)
                pub   = re.search(r"<pubDate>(.*?)</pubDate>", item)
                src   = re.search(r"<source[^>]*>(.*?)</source>", item)
                if title:
                    articles.append({
                        "title":  title.group(1).strip(),
                        "url":    link.group(1).strip() if link else "",
                        "date":   pub.group(1)[:16] if pub else "",
                        "source": src.group(1).strip() if src else "Google News",
                    })
            return articles
        except Exception:
            return []
    return _cached(f"news:{company}", _fetch)


# ── Crunchbase (public search, no API key) ────────────────────────

def fetch_crunchbase_signals(company: str) -> dict:
    """Scrape public Crunchbase org page for funding/employee signals."""
    def _fetch():
        slug = re.sub(r"[^a-z0-9]", "-", company.lower()).strip("-")
        url  = f"https://www.crunchbase.com/organization/{slug}"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=12)
            text = r.text
            # Funding mentions
            funding_m = re.search(
                r"total funding.*?\$([\d,.]+)\s*(M|B|K|million|billion|thousand)?",
                text, re.IGNORECASE
            )
            funding = ""
            if funding_m:
                val, unit = funding_m.group(1), (funding_m.group(2) or "").upper()
                funding = f"${val}{unit}"

            # Employee count range
            emp_m = re.search(
                r"([\d,]+)[-–]?([\d,]+)?\s*(employees?|people|staff)",
                text, re.IGNORECASE
            )
            employees = emp_m.group(0)[:40] if emp_m else ""

            # Founded year
            founded_m = re.search(r"[Ff]ounded[:\s]+([\d]{4})", text)
            founded = founded_m.group(1) if founded_m else ""

            return {"funding": funding, "employees": employees, "founded": founded, "url": url}
        except Exception:
            return {}
    return _cached(f"cb:{company}", _fetch)


# ── HackerNews mention search ─────────────────────────────────────

def fetch_hn_mentions(company: str, max_results: int = 5) -> list[dict]:
    """Search HackerNews for recent mentions of this company."""
    def _fetch():
        try:
            r = requests.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": company, "tags": "story", "hitsPerPage": max_results},
                timeout=8,
            )
            r.raise_for_status()
            results = []
            for hit in r.json().get("hits", []):
                results.append({
                    "title":  hit.get("title", ""),
                    "url":    hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
                    "points": hit.get("points", 0),
                    "date":   (hit.get("created_at") or "")[:10],
                })
            return results
        except Exception:
            return []
    return _cached(f"hn:{company}", _fetch)


# ── Tech stack signals via BuiltWith-style header scraping ─────────

def fetch_tech_signals(company_website: str) -> list[str]:
    """Detect tech signals from a company's public website headers and HTML."""
    def _fetch():
        if not company_website:
            return []
        url = company_website if company_website.startswith("http") else f"https://{company_website}"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
            signals = set()
            # Response headers
            headers = {k.lower(): v.lower() for k, v in r.headers.items()}
            server = headers.get("server", "")
            powered = headers.get("x-powered-by", "")
            if "nginx" in server:    signals.add("nginx")
            if "apache" in server:   signals.add("apache")
            if "cloudflare" in server: signals.add("Cloudflare")
            if "php" in powered:     signals.add("PHP")
            if "express" in powered: signals.add("Node.js/Express")
            if "next.js" in powered: signals.add("Next.js")
            # HTML content
            text = r.text.lower()
            _tech_map = {
                "react":           "React",
                "vue":             "Vue.js",
                "angular":         "Angular",
                "next.js":         "Next.js",
                "gatsby":          "Gatsby",
                "webpack":         "Webpack",
                "graphql":         "GraphQL",
                "apollo":          "Apollo/GraphQL",
                "stripe":          "Stripe (payments)",
                "segment":         "Segment (analytics)",
                "intercom":        "Intercom (support)",
                "datadog":         "Datadog (monitoring)",
                "sentry":          "Sentry (error tracking)",
                "amplitude":       "Amplitude (analytics)",
                "hubspot":         "HubSpot (CRM)",
                "salesforce":      "Salesforce (CRM)",
                "kubernetes":      "Kubernetes",
                "docker":          "Docker",
                "aws":             "AWS",
                "vercel":          "Vercel",
                "supabase":        "Supabase",
                "firebase":        "Firebase",
                "algolia":         "Algolia (search)",
                "twilio":          "Twilio (comms)",
                "openai":          "OpenAI API",
                "anthropic":       "Anthropic/Claude",
                "langchain":       "LangChain",
                "pinecone":        "Pinecone (vector DB)",
                "postgres":        "PostgreSQL",
                "mongodb":         "MongoDB",
            }
            for keyword, label in _tech_map.items():
                if keyword in text:
                    signals.add(label)
            return sorted(signals)[:15]
        except Exception:
            return []
    return _cached(f"tech:{company_website}", _fetch)


# ── Glassdoor rating via public search ───────────────────────────

def fetch_glassdoor_signals(company: str) -> dict:
    """Try to find Glassdoor rating from public search result snippets."""
    def _fetch():
        try:
            url = f"https://www.glassdoor.com/Search/results.htm?keyword={requests.utils.quote(company)}"
            r = requests.get(url, headers=_HEADERS, timeout=10)
            rating_m = re.search(r"(\d\.\d)\s*(?:out of 5|/5|\*{1,5})", r.text)
            if rating_m:
                return {"rating": rating_m.group(1), "source": "Glassdoor"}
            return {}
        except Exception:
            return {}
    return _cached(f"gd:{company}", _fetch)


# ── Job posting velocity (via Jobicy) ────────────────────────────

def fetch_hiring_velocity(company: str) -> dict:
    """Count current open postings for this company as a hiring signal."""
    def _fetch():
        try:
            r = requests.get(
                "https://jobicy.com/api/v2/remote-jobs",
                params={"count": 100, "company": company},
                timeout=8,
            )
            r.raise_for_status()
            jobs = r.json().get("jobs", [])
            titles = [j.get("jobTitle", "") for j in jobs]
            return {
                "open_roles": len(jobs),
                "sample_roles": titles[:6],
            }
        except Exception:
            return {"open_roles": 0, "sample_roles": []}
    return _cached(f"vel:{company}", _fetch)


# ── Claude synthesis ──────────────────────────────────────────────

def synthesize_dossier(
    company: str,
    role: str,
    news: list[dict],
    hn_mentions: list[dict],
    cb_signals: dict,
    tech_signals: list[str],
    hiring: dict,
    resume_text: str = "",
) -> dict:
    """
    Use Claude Sonnet to synthesize all raw signals into a structured company dossier.
    Returns dict with keys: summary, culture_read, why_apply, red_flags, talking_points,
    likely_interview_qs, company_stage, recruiter_angle.
    """
    import json
    from claude_ai import _get_client, _sanitize

    resume_ctx  = _sanitize(resume_text, 1500)
    company_s   = _sanitize(company, 100)
    role_s      = _sanitize(role, 100)

    news_text = "\n".join(
        f"- [{a['date']}] {a['title']} ({a['source']})" for a in news[:6]
    ) or "No recent news found."

    hn_text = "\n".join(
        f"- [{h['date']}] {h['title']} ({h['points']} pts)" for h in hn_mentions[:4]
    ) or "No HN mentions."

    cb_text = (
        f"Funding: {cb_signals.get('funding','unknown')} | "
        f"Employees: {cb_signals.get('employees','unknown')} | "
        f"Founded: {cb_signals.get('founded','unknown')}"
    ) if cb_signals else "No Crunchbase data found."

    tech_text = ", ".join(tech_signals) if tech_signals else "Could not detect tech stack."

    hiring_text = (
        f"{hiring.get('open_roles', 0)} open roles detected. "
        f"Sample: {', '.join(hiring.get('sample_roles', []))}"
    ) if hiring.get("open_roles") else "No current job postings found via Jobicy."

    client = _get_client()
    if client is None:
        return {
            "summary": "Claude API not available — add ANTHROPIC_API_KEY to .env",
            "culture_read": "", "why_apply": "", "red_flags": [],
            "talking_points": [], "likely_interview_qs": [],
            "company_stage": "", "recruiter_angle": "",
        }

    system = (
        "You are a senior career strategist and company analyst. "
        "You synthesize real signals (news, funding, tech stack, hiring velocity) into actionable intelligence. "
        "Be specific and direct. Return valid JSON only — no markdown fences."
    )
    user = f"""Synthesize company intelligence for {company_s} and the {role_s} role.

RECENT NEWS:
{news_text}

HACKERNEWS MENTIONS:
{hn_text}

COMPANY DATA:
{cb_text}

TECH STACK SIGNALS:
{tech_text}

HIRING VELOCITY:
{hiring_text}

CANDIDATE RESUME (for tailoring):
{resume_ctx or 'Not provided'}

Return a JSON object with exactly these keys:
- "summary": string — 2-3 sentence company overview: what they do, stage, momentum (cite specific news if relevant)
- "company_stage": string — one of: "early-stage startup", "growth-stage", "public company", "enterprise", "unknown"
- "culture_read": string — 2-3 sentences reading the culture from signals (hiring pace, news tone, tech choices)
- "why_apply": list of 3 strings — specific reasons this candidate (based on resume) would be a strong fit here
- "red_flags": list of up to 3 strings — genuine risks or concerns from the signals (empty list if none)
- "talking_points": list of 4 strings — specific things to reference in the interview or cover letter from the news/signals
- "likely_interview_qs": list of 4 strings — interview questions this company will likely ask based on their signals
- "recruiter_angle": string — one tactical sentence: what angle to lead with when reaching out to their recruiter

Return ONLY valid JSON."""

    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        ) as s:
            full = ""
            for chunk in s.text_stream:
                full += chunk
        cleaned = re.sub(r"^```(?:json)?\s*", "", full.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {
        "summary": "Analysis failed — try again.",
        "culture_read": "", "why_apply": [], "red_flags": [],
        "talking_points": [], "likely_interview_qs": [],
        "company_stage": "unknown", "recruiter_angle": "",
    }


# ── Main entry point ──────────────────────────────────────────────

def research_company(
    company: str,
    role: str = "",
    company_website: str = "",
    resume_text: str = "",
    progress_callback=None,
) -> dict:
    """
    Full agentic company research pipeline.
    Fetches all signals concurrently then synthesizes with Claude.
    progress_callback(step: str, pct: int) is called at each stage.
    Returns the synthesized dossier dict plus raw_signals.
    """
    import concurrent.futures

    def _cb(msg, pct):
        if progress_callback:
            try:
                progress_callback(msg, pct)
            except Exception:
                pass

    _cb("Fetching news…", 10)

    # Concurrent data fetch
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        f_news    = pool.submit(fetch_company_news, company)
        f_cb      = pool.submit(fetch_crunchbase_signals, company)
        f_hn      = pool.submit(fetch_hn_mentions, company)
        f_tech    = pool.submit(fetch_tech_signals, company_website) if company_website else None
        f_hiring  = pool.submit(fetch_hiring_velocity, company)

        _cb("Pulling HackerNews signals…", 30)
        news    = f_news.result()
        _cb("Checking funding data…", 50)
        cb_data = f_cb.result()
        hn_data = f_hn.result()
        tech    = f_tech.result() if f_tech else []
        _cb("Analyzing hiring velocity…", 70)
        hiring  = f_hiring.result()

    _cb("Synthesizing with Claude Sonnet…", 85)

    dossier = synthesize_dossier(
        company=company,
        role=role,
        news=news,
        hn_mentions=hn_data,
        cb_signals=cb_data,
        tech_signals=tech,
        hiring=hiring,
        resume_text=resume_text,
    )

    _cb("Done.", 100)

    return {
        **dossier,
        "raw": {
            "news":    news,
            "hn":      hn_data,
            "cb":      cb_data,
            "tech":    tech,
            "hiring":  hiring,
        },
        "company": company,
        "role":    role,
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
