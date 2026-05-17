# Claude Code Context — CareerIQ / job_finder

## Run command
```bash
cd ~/Documents/Projects/job_finder && streamlit run app.py
```

## Backup system
- Script: `bash ~/Documents/Projects/job_finder/backup.sh`
- Saves to: `backups/YYYYMMDD_HHMMSS/` — captures all .py files, pages/, tests/, .env, DBs, config files
- Keeps 10 most recent snapshots, prunes older ones automatically
- **"Save" or "backup" = run `bash ~/Documents/Projects/job_finder/backup.sh`**

## Architecture: 40 Python files total

### Entry points
| File | Role |
|------|------|
| `app.py` | Streamlit entry — `st.navigation()` multi-page setup, auth gate, CSS injection |
| `api.py` | FastAPI REST API — CORS locked, fail-secure auth, payload size limits |

### Core backend
| File | Role |
|------|------|
| `resume_parser.py` | PDF/DOCX text extraction, skill matching, alias resolution |
| `resume_editor.py` | Bullet scoring, buzzword detection, section analysis |
| `scorer.py` | Semantic job scoring — sentence-transformers + keyword fallback |
| `tracker.py` | SQLite application pipeline — thread-safe with lock + INSERT OR IGNORE |
| `claude_ai.py` | All Claude API calls — cover letter, LinkedIn, interview, career intel |
| `writing_suite.py` | 23-tool writing suite — Claude-first, template fallback |
| `ai_tools.py` | ATS scanner, skill gap analysis, interview question generation |
| `job_fetcher.py` | Multi-source job search — Adzuna, Jobicy, Muse, Remotive, Arbeitnow |
| `job_market.py` | FRED macro data, BLS projections, RSS news feeds |
| `market_intel.py` | HackerNews hiring signals, GitHub trending, Jobicy skill counts |
| `linkedin_editor.py` | LinkedIn headline/about/DM generation, profile scoring |
| `salary_intel.py` | Role-based salary estimates with city cost-of-living multipliers |
| `vector_store.py` | ChromaDB semantic job store |
| `profile_store.py` | SQLite user profiles + STAR stories persistence |
| `analytics.py` | Usage event tracking (SQLite) |
| `auth.py` | bcrypt password hashing, user accounts |
| `career_level.py` | Career level detection (entry/mid/senior/executive) |
| `pdf_export.py` | Resume report + writing output PDF generation |
| `charlotte_jobs.py` | Charlotte-specific job sources |
| `job_alerts.py` | ntfy push notification system |
| `background_scanner.py` | Scheduled job scanner daemon |
| `utils.py` | CSS injection, shared HTML helpers, xe() XSS escaping |

### Pages (pages/)
| File | Page |
|------|------|
| `1_Resume.py` | Resume Analyzer — upload, score, bullet coach, tailor, vault |
| `2_Jobs.py` | Job Search — multi-source search, filters, fit scoring |
| `3_LinkedIn.py` | LinkedIn Optimizer — headlines, about, cold DMs, salary negotiation |
| `4_Write.py` | Writing Suite — 23 AI writing tools |
| `5_Interview.py` | Interview Prep — question bank, STAR stories, AI coaching |
| `6_Track.py` | Application Tracker — kanban pipeline, follow-up calendar |
| `7_Market.py` | Market Intelligence — FRED data, BLS projections, HN signals |
| `8_Profile.py` | My Profile — preferences, scanner config, job alerts |
| `9_Apply.py` | Apply Package — ATS scan + cover letter + thank-you bundle |
| `10_Stats.py` | Analytics — usage stats, scanner history, pipeline overview |

### Tests (tests/)
- 92 passing tests (non-slow suite)
- Run: `pytest tests/ -m "not slow" -q`

## Key files
- `.env` — API keys (ANTHROPIC_API_KEY, FRED_KEY, GITHUB_TOKEN, etc.)
- `applications.db` — application pipeline SQLite
- `users.db` — user accounts SQLite
- `analytics.db` — usage event tracking SQLite
- `requirements.txt` — Python dependencies
- `Makefile` — `make run`, `make test`, `make lint`

## API keys (all in .env)
- `ANTHROPIC_API_KEY` — required for all AI features
- `FRED_KEY` — FRED economic data (Market page)
- `GITHUB_TOKEN` — GitHub trending (optional, raises rate limit)
- `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` — live job listings (optional)
- `JSEARCH_API_KEY` — JSearch job listings (optional)

## Rules
- Python: `/opt/anaconda3/bin/python3`
- Never read all pages at once — search for specific functions
- Parameterized SQL only (no f-string interpolation with user data)
- `xe()` from utils for all user-facing HTML rendering (XSS protection)
- `_sanitize()` in claude_ai.py for all user input before Claude API calls
- Threading lock in tracker.py for all DB writes
- Streamlit uses `st.navigation()` — never call `st.set_page_config()` in page files
