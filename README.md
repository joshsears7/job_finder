# CareerIQ

**AI-powered career intelligence platform** — upload your resume and get instant scoring, semantic job matching, tailored cover letters, ATS gap analysis, interview prep, and a full application pipeline tracker.

[![Test Suite](https://github.com/joshuasears/job_finder/actions/workflows/test.yml/badge.svg)](https://github.com/joshuasears/job_finder/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32-red)
![Claude AI](https://img.shields.io/badge/Claude-Anthropic-blueviolet)

---

## Live Demo

> Live deployment coming soon. Clone the repo and run locally in under 2 minutes — see Setup below.

---

## What It Does

| Feature | Description |
|---|---|
| **Resume Scoring** | Parses uploaded PDFs/DOCX and scores against 53+ signals — keyword density, action verbs, quantification, ATS formatting |
| **Semantic Job Matching** | ChromaDB vector search finds jobs that match your *actual experience*, not just keyword overlap |
| **Apply Engine** | One-click package: ATS scan, tailored cover letter, targeted resume bullets, and a post-interview thank-you note |
| **LinkedIn Optimizer** | Scores your LinkedIn profile, rewrites your headline/about/skills section for target roles |
| **Writing Suite** | 23 AI-powered writing tools — cold outreach, networking emails, salary negotiation, offer comparison |
| **Interview Prep** | Generates likely questions from the job description; STAR-method story builder |
| **Application Tracker** | Kanban-style pipeline with follow-up reminders and a built-in networking CRM |
| **Market Intelligence** | BLS 10-year projections, FRED economic indicators, live HackerNews hiring signals, salary benchmarks |
| **Resume A/B Testing** | Track multiple resume versions against real application outcomes |
| **Analytics Dashboard** | Session activity, scanner history, application funnel metrics |

---

## Tech Stack

- **Frontend** — Streamlit (multi-page, custom CSS design system)
- **AI** — Anthropic Claude API (claude-sonnet-4-6 / claude-haiku-4-5) for all generative tasks
- **Semantic Search** — ChromaDB + `sentence-transformers/all-MiniLM-L6-v2`
- **Auth** — bcrypt password hashing, backward-compatible SHA256 migration path
- **Storage** — PostgreSQL on cloud (Neon) · SQLite locally — dual-mode via `db.py` abstraction
- **PDF** — pdfplumber with two-column layout detection · fpdf2 for cover letter/package export
- **Data** — FRED API, BLS static projections, Adzuna job listings API, RapidAPI JSearch
- **REST API** — FastAPI layer (`api.py`) for headless/server-to-server access
- **Testing** — pytest, 92 tests across 4 modules, `@pytest.mark.slow` for model-gated tests
- **CI** — GitHub Actions (lint + fast test suite on every push)
- **Deploy** — Railway (nixpacks, auto-restart)

---

## Architecture

```mermaid
graph TD
    subgraph Input
        PDF[PDF / DOCX Upload]
        JD[Job Description]
    end

    subgraph Core["Core Pipeline"]
        RP[resume_parser.py<br/>PDF/DOCX → structured profile]
        SC[scorer.py<br/>Semantic + keyword + title scoring<br/>Adaptive cosine normalization]
        RE[resume_editor.py<br/>53-signal bullet analysis<br/>Career level detection]
        GJ[ghost_score()<br/>Stale listing detection]
    end

    subgraph AI["AI Layer — Claude"]
        HAI[claude_ai.py<br/>Haiku — fast tools<br/>Sonnet — quality outputs<br/>Streaming via st.write_stream]
        WS[writing_suite.py<br/>23 AI writing tools]
        CR[company_research.py<br/>Agentic intel: news · funding · tech stack]
        EV[eval_engine.py<br/>Output quality scoring<br/>Grounding · Specificity · Relevance]
    end

    subgraph Data["Data Sources"]
        JF[job_fetcher.py<br/>6 sources · ThreadPoolExecutor<br/>SequenceMatcher dedup]
        MI[market_intel.py<br/>HackerNews · GitHub trending]
        JM[job_market.py<br/>FRED API · BLS projections]
        SI[salary_intel.py<br/>CoL-adjusted benchmarks]
    end

    subgraph Storage["Persistence"]
        DB[(SQLite<br/>applications · users · analytics)]
        CV[(ChromaDB<br/>Semantic job index)]
        AB[(ab_testing.db<br/>Resume A/B outcomes)]
        EDB[(eval_results.db<br/>AI quality history)]
    end

    subgraph Interfaces["Interfaces"]
        APP[app.py<br/>Streamlit 13-page multi-user app]
        API[api.py<br/>FastAPI REST · /metrics · /score · /jobs]
        MCP[mcp_server.py<br/>MCP tools — Claude Desktop · Cursor]
        LA[linkedin_applier.py<br/>Playwright Easy Apply agent]
    end

    PDF --> RP --> SC --> APP
    JD  --> SC
    SC  --> CV
    JF  --> SC
    JF  --> DB
    RP  --> RE --> APP
    RP  --> HAI --> WS --> APP
    CR  --> APP
    EV  --> EDB
    HAI --> EV
    MI  --> APP
    JM  --> APP
    SI  --> APP
    DB  --> APP
    AB  --> APP
    APP --> API
    APP --> MCP
    APP --> LA
```

### File map

| File | Role |
|---|---|
| `app.py` | Streamlit entry — auth gate, 13-page navigation |
| `scorer.py` | Semantic scoring: sentence-transformers + keyword + title overlay, adaptive normalization |
| `resume_parser.py` | PDF/DOCX → structured profile with skill alias resolution |
| `resume_editor.py` | 53-signal bullet analysis, career level detection, achievement density |
| `claude_ai.py` | All Claude calls: Haiku for speed, Sonnet for quality, streaming generators |
| `job_fetcher.py` | 6 concurrent sources, SequenceMatcher dedup, background ChromaDB indexing |
| `company_research.py` | Agentic company intel: news, funding, HackerNews, tech stack, hiring velocity |
| `eval_engine.py` | Heuristic LLM output evaluation: grounding, specificity, relevance, tone |
| `ab_testing.py` | Resume A/B outcome tracking with response rate correlation |
| `mcp_server.py` | MCP server — 7 tools for Claude Desktop / Cursor integration |
| `linkedin_applier.py` | Playwright Easy Apply agent with human-in-the-loop approval |
| `writing_suite.py` | 23 AI writing tools |
| `api.py` | FastAPI REST: /score, /jobs/search, /metrics (Prometheus-compatible) |

---

## Quick Start

```bash
git clone https://github.com/joshuasears/job_finder
cd job_finder

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

streamlit run app.py
```

Open `http://localhost:8501` — click **Try Live Demo** to explore without creating an account.

### Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | All AI features |
| `DATABASE_URL` | Cloud only | PostgreSQL connection string (Neon/Supabase) — falls back to SQLite locally |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Optional | Live job listings |
| `JSEARCH_API_KEY` | Optional | Additional job source (RapidAPI) |
| `FRED_KEY` | Optional | Economic market data |

---

## Running Tests

```bash
pytest                          # fast tests only (no model required)
pytest -m slow                  # include model-dependent tests
pytest --cov=. --cov-report=term-missing
```

The test suite covers the scoring engine, tracker CRUD, job fetcher, and salary intelligence — 92 tests across 4 modules.

---

## Deployment

The repo ships with `railway.toml` and `nixpacks.toml` for one-command Railway deployment:

```bash
railway up
```

The nixpacks build pre-downloads the sentence-transformers model at build time so cold starts are fast.
