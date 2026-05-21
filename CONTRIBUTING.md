# Contributing to CareerIQ

## Setup

```bash
git clone https://github.com/joshsears7/job_finder
cd job_finder

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add ANTHROPIC_API_KEY to .env — required for AI features
```

Run the app:
```bash
streamlit run app.py
```

## Running tests

```bash
pytest tests/ -m "not slow" -q    # fast suite, no API key needed
pytest -m slow                     # model-dependent tests (requires ANTHROPIC_API_KEY)
pytest --cov=. --cov-report=term-missing
```

The CI pipeline runs the fast suite on every push. All 92 fast tests must pass before merging.

## Code standards

**Security — non-negotiable:**
- Parameterized SQL only — never interpolate user data into query strings
- All user-facing HTML must go through `xe()` from `utils.py`
- All user input passed to the Claude API must go through `_sanitize()` in `claude_ai.py`
- All DB writes in `tracker.py` must acquire `_db_lock`

**Style:**
- No comments explaining what the code does — name things so they're self-evident
- No feature flags or backwards-compatibility shims — just change the code
- No error handling for scenarios that can't happen — only validate at system boundaries

**Database:**
- Never import `sqlite3` or `psycopg2` directly in page files — use `db.py`
- Use `db.P` as the query placeholder (`?` on SQLite, `%s` on PostgreSQL)
- Test both backends if touching `db.py`

## Project structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for a full explanation of the system design, key decisions, and file map.

## Adding a new page

1. Create `pages/N_Name.py` — follow the existing naming convention
2. Do **not** call `st.set_page_config()` in the page file — it's called once in `app.py`
3. Add the page to `st.navigation()` in `app.py`
4. Import only from the backend modules listed in ARCHITECTURE.md — no raw DB access

## Adding a new writing tool

1. Add an entry to `PROMPT_CATALOG` in `writing_suite.py`
2. The `_generate_with_claude()` function handles prompting, sanitization, and fallback automatically
3. Expose it in `pages/4_Write.py`

## Reporting issues

Open an issue at [github.com/joshsears7/job_finder/issues](https://github.com/joshsears7/job_finder/issues) with:
- What you expected
- What happened
- Steps to reproduce
- Python version and OS
