"""
job_market.py
-------------
Live economic data from FRED + BLS projections + RSS news.
Requires FRED_KEY in .env (free at fred.stlouisfed.org/docs/api/api_key.html).
"""

import os
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FRED_KEY = os.getenv("FRED_KEY", "")
FRED_OBS  = "https://api.stlouisfed.org/fred/series/observations"

# ── FRED series ─────────────────────────────────────────────────

MACRO_SERIES = {
    "Unemployment Rate (%)":          "UNRATE",
    "Job Openings (thousands)":       "JTSJOL",
    "Hires (thousands)":              "JTSHIL",
    "Layoffs & Discharges (k)":       "JTSLDL",
    "Nonfarm Payrolls (thousands)":   "PAYEMS",
}

SECTOR_SERIES = {
    "Technology / Info":        "USINFO",
    "Professional Services":    "CES6000000001",
    "Healthcare":               "CES6562000001",
    "Financial Services":       "CES5500000001",
    "Retail Trade":             "CES4200000001",
    "Manufacturing":            "MANEMP",
    "Construction":             "USCONS",
    "Leisure & Hospitality":    "CES7000000001",
}

# ── BLS 2023-2033 Employment Projections (official, semi-static) ─

BLS_PROJECTIONS = {
    "fastest_growing": [
        ("Wind Turbine Technicians",          "+60%", "Clean Energy"),
        ("Nurse Practitioners",               "+46%", "Healthcare"),
        ("Data Scientists",                   "+36%", "Tech / Analytics"),
        ("Information Security Analysts",     "+32%", "Cybersecurity"),
        ("Medical & Health Services Managers","+28%", "Healthcare"),
        ("Software Developers",               "+25%", "Tech"),
        ("Operations Research Analysts",      "+23%", "Analytics / Consulting"),
        ("Financial Examiners",               "+20%", "Finance / Compliance"),
        ("Market Research Analysts",          "+19%", "Marketing / Data"),
        ("Management Analysts",               "+11%", "Consulting / Strategy"),
    ],
    "fastest_declining": [
        ("Word Processors / Typists",   "-31%", "Admin"),
        ("Travel Agents",               "-26%", "Travel"),
        ("Data Entry Keyers",           "-20%", "Admin"),
        ("Postal Service Workers",      "-15%", "Government / Logistics"),
        ("Nuclear Reactor Operators",   "-16%", "Energy"),
        ("Switchboard Operators",       "-15%", "Telecom"),
    ],
    "hot_sectors_narrative": [
        ("🤖 AI / Machine Learning",
         "Every industry is integrating AI. Demand for people who can work with AI tools — not just build them — is exploding. Business + tech hybrid backgrounds are extremely sought after."),
        ("💊 Healthcare Technology",
         "Aging population + digital transformation driving 10+ year hiring boom. Health informatics, digital health, and healthcare analytics are some of the fastest-growing roles."),
        ("🔒 Cybersecurity",
         "Every breach headline is a job posting. The US has 700,000+ unfilled cybersecurity roles. Your CISCO cert is a real entry point here."),
        ("💰 Fintech & Financial Services",
         "Digital payments, crypto regulation, and algorithmic finance are reshaping banks. Python-fluent business students are rare and valuable."),
        ("🌱 Clean Energy",
         "Inflation Reduction Act is pumping $370B into clean energy. Project management, business development, and operations roles are surging."),
        ("📊 Business Analytics",
         "Data literacy is now table stakes. Companies are hiring analysts who bridge business and data — exactly the profile you're building."),
    ],
}

# ── RSS news feeds ───────────────────────────────────────────────

NEWS_FEEDS = [
    ("BBC Business",          "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("NPR Economy",           "https://feeds.npr.org/1017/rss.xml"),
    ("MarketWatch Top",       "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Wall Street Journal",   "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml"),
]

JOB_KEYWORDS = {
    "hiring", "layoff", "layoffs", "jobs", "employment", "unemployment",
    "workforce", "workers", "labor", "recession", "economy", "tech",
    "salary", "wages", "remote", "artificial intelligence", "ai",
}


def _fetch_fred(series_id, limit=3):
    if not FRED_KEY:
        return []
    try:
        r = requests.get(FRED_OBS, params={
            "series_id": series_id,
            "api_key": FRED_KEY,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }, timeout=10)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        data = []
        for o in reversed(obs):
            raw = o.get("value", ".")
            if raw != "." and raw is not None:
                try:
                    data.append({"date": o["date"], "value": float(raw)})
                except (ValueError, TypeError):
                    pass
        return data
    except Exception:
        return []


def _fetch_rss(url, max_items=6):
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        # Disable entity resolution to prevent XXE attacks
        parser = ET.XMLParser()
        parser.entity = {}
        root = ET.fromstring(r.content, parser)
        items = root.findall(".//item")
        out = []
        for item in items:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            desc  = item.findtext("description", "").strip()
            date  = item.findtext("pubDate", "")[:16]
            # Only keep job/economy relevant headlines
            combined = (title + " " + desc).lower()
            if any(kw in combined for kw in JOB_KEYWORDS):
                out.append({"title": title, "link": link, "desc": desc, "date": date})
            if len(out) >= max_items:
                break
        return out
    except Exception:
        return []


def get_macro_snapshot():
    """Latest value + prior-period delta for each macro series."""
    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_fred, sid, 3): name
                   for name, sid in MACRO_SERIES.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            data = fut.result()
            if not data:
                continue
            latest = data[-1]["value"]
            if len(data) >= 2:
                prev  = data[-2]["value"]
                delta = round(latest - prev, 3)
            else:
                prev  = latest
                delta = None
            results[name] = {
                "latest": latest,
                "prev":   prev,
                "delta":  delta,
                "trend":  data,
            }
    return results


def get_sector_changes():
    """Month-over-month employment change by sector (thousands of jobs)."""
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_fred, sid, 3): name
                   for name, sid in SECTOR_SERIES.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            data = fut.result()
            if len(data) < 2:
                continue
            change = round(data[-1]["value"] - data[-2]["value"], 1)
            results[name] = {
                "latest": data[-1]["value"],
                "change": change,
                "date":   data[-1]["date"],
            }
    return results


def get_job_news():
    """Fetch job/economy headlines from multiple RSS feeds."""
    all_news = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_fetch_rss, url, 6): name
                   for name, url in NEWS_FEEDS}
        for fut in as_completed(futures):
            source = futures[fut]
            for item in fut.result():
                item["source"] = source
                all_news.append(item)
    # Sort by recency (date string), deduplicate by title
    seen = set()
    unique = []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
    return unique[:15]


def get_full_market_data():
    """Fetch everything in parallel. Returns dict ready for Streamlit."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        macro_fut  = pool.submit(get_macro_snapshot)
        sector_fut = pool.submit(get_sector_changes)
        news_fut   = pool.submit(get_job_news)

        macro   = macro_fut.result()
        sectors = sector_fut.result()
        news    = news_fut.result()

    return {
        "macro":       macro,
        "sectors":     sectors,
        "news":        news,
        "projections": BLS_PROJECTIONS,
        "fetched_at":  datetime.now().strftime("%b %d %Y, %I:%M %p"),
    }
