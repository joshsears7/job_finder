# CareerIQ — Architecture

## Overview

CareerIQ is a multi-page Streamlit application backed by a FastAPI REST layer. It uses Claude (Anthropic) for all generative AI tasks and sentence-transformers for local semantic search. Storage is dual-mode: PostgreSQL in production (Neon) and SQLite locally, abstracted behind a single `db.py` layer so no page file ever touches a connection string.

## Request flow

```
Browser → Streamlit (app.py)
             │
             ├── resume_parser.py    PDF/DOCX → structured profile
             ├── resume_editor.py    53-signal bullet analysis
             ├── scorer.py           Semantic + keyword + title scoring
             ├── claude_ai.py        All Claude API calls (streaming)
             ├── writing_suite.py    23 AI writing tools
             ├── job_fetcher.py      6 concurrent job sources
             ├── tracker.py          Application pipeline (thread-safe)
             └── db.py               PostgreSQL / SQLite abstraction

External:   FastAPI (api.py) — REST endpoints for headless access
            MCP server (mcp_server.py) — Claude Desktop / Cursor tools
```

## Key design decisions

**Dual-mode database (`db.py`)**
All DB access goes through `db.py`. It detects `DATABASE_URL` in the environment: if present, connects to PostgreSQL via psycopg2; otherwise uses SQLite. The `db.P` constant holds the correct placeholder (`%s` vs `?`) so query strings work unchanged on both backends. Page files never import sqlite3 or psycopg2 directly.

**Thread safety in `tracker.py`**
The background job scanner runs in a daemon thread alongside the Streamlit server. All write functions in `tracker.py` acquire `_db_lock` (a `threading.Lock`) before touching the database, preventing concurrent-write races on SQLite. PostgreSQL handles its own concurrency but the lock is kept for consistency.

**Semantic scoring (`scorer.py`)**
Job-resume matching uses `sentence-transformers/all-MiniLM-L6-v2` for embedding, with cosine similarity normalized to 0–100. A keyword overlap layer and title-match bonus are added on top. The model is loaded once at startup and cached in `st.session_state` to avoid re-loading on every rerender.

**Two-column PDF detection (`resume_parser.py`)**
pdfplumber exposes per-word bounding boxes. If fewer than 5% of words physically cross the page centerline, the page is split into left and right columns and extracted separately (left first), preserving reading order for two-column resume templates. Single-column pages fall back to pdfplumber's default extraction.

**Claude API usage (`claude_ai.py`)**
- Haiku for fast, high-volume tasks (ATS scanning, skill gap, short summaries)
- Sonnet for quality outputs (cover letters, company research, interview coaching)
- All user input is passed through `_sanitize()` before embedding in prompts
- Streaming responses use `st.write_stream()` for real-time output

**Security**
- All HTML rendered via `st.markdown(..., unsafe_allow_html=True)` passes through `xe()` (XSS escaping) from `utils.py`
- All SQL queries use parameterized placeholders — no f-string interpolation of user data
- API endpoints protected by `X-API-Key` header; rate-limited to 60 req/min per IP
- Passwords hashed with bcrypt; legacy SHA256 hashes migrated on login

## File map

| Layer | Files |
|---|---|
| Entry points | `app.py`, `api.py`, `mcp_server.py` |
| Pages | `pages/1_Resume.py` → `pages/12_AutoApply.py` |
| AI | `claude_ai.py`, `writing_suite.py`, `company_research.py`, `eval_engine.py` |
| Scoring | `scorer.py`, `resume_editor.py`, `resume_parser.py`, `ai_tools.py` |
| Data | `job_fetcher.py`, `job_market.py`, `market_intel.py`, `salary_intel.py` |
| Storage | `db.py`, `tracker.py`, `profile_store.py`, `analytics.py`, `auth.py` |
| Utilities | `utils.py`, `pdf_export.py`, `career_level.py`, `ab_testing.py` |
| Background | `background_scanner.py`, `job_alerts.py` |

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY
streamlit run app.py
```

## Tests

```bash
pytest tests/ -m "not slow" -q    # 92 fast tests, no model required
pytest -m slow                     # model-dependent tests
pytest --cov=. --cov-report=term-missing
```

Test modules cover: resume scoring (`test_scorer.py`), application tracker CRUD (`test_tracker.py`), job fetcher deduplication (`test_job_fetcher.py`), salary intelligence (`test_salary.py`).
