"""
api.py — CareerIQ REST API
--------------------------
FastAPI layer exposing resume scoring, job matching, and analytics.
Run standalone: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional
import os
import time
import threading
from collections import defaultdict

import analytics
import tracker
import auth as _auth
import scorer
import vector_store as vs

app = FastAPI(
    title="CareerIQ API",
    description="Resume scoring, job matching, and career analytics",
    version="1.0.0",
)

_DEFAULT_ORIGINS = "http://localhost:8501,https://*.hf.space,https://*.up.railway.app,https://*.streamlit.app"
_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

_API_KEY = os.getenv("CAREERIQ_API_KEY", "")

# ── Rate limiter (60 req/min per IP) ─────────────────────────────
_rl_lock   = threading.Lock()
_rl_counts: dict = defaultdict(lambda: [0, 0.0])  # ip -> [count, window_start]
_RL_LIMIT  = int(os.getenv("RATE_LIMIT_RPM", "60"))
_RL_WINDOW = 60.0

def _rate_limit(request: Request):
    ip  = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rl_lock:
        count, window_start = _rl_counts[ip]
        if now - window_start >= _RL_WINDOW:
            _rl_counts[ip] = [1, now]
        else:
            if count >= _RL_LIMIT:
                raise HTTPException(status_code=429, detail="Rate limit exceeded — 60 requests per minute")
            _rl_counts[ip][0] += 1


def _check_key(x_api_key: str = Header(default="")):
    # Fail-secure: if no key is configured, all protected routes require a non-empty header
    # that won't match, preventing accidental open access.
    if not _API_KEY:
        raise HTTPException(status_code=503, detail="API key not configured on server")
    if x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ── Models ────────────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    resume_text: str
    job_description: str
    job_title: Optional[str] = ""

class SearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 10

class IndexJobRequest(BaseModel):
    job_id: str
    title: str
    company: str
    description: str
    source: Optional[str] = ""
    location: Optional[str] = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str


# ── Health ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "CareerIQ API"}


# ── Auth ──────────────────────────────────────────────────────────

@app.post("/auth/register")
def register(req: RegisterRequest, _rl=Depends(_rate_limit)):
    result = _auth.register(req.email, req.name, req.password)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"user_id": result["user_id"], "name": req.name}

@app.post("/auth/login")
def login(req: LoginRequest, _rl=Depends(_rate_limit)):
    result = _auth.login(req.email, req.password)
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["error"])
    return {"user_id": result["user_id"], "name": result["name"]}


# ── Resume Scoring ────────────────────────────────────────────────

@app.post("/score", dependencies=[Depends(_check_key)])
def score_resume(req: ScoreRequest):
    """Score a resume against a job description. Returns 0-100."""
    if not req.resume_text.strip() or not req.job_description.strip():
        raise HTTPException(status_code=400, detail="resume_text and job_description required")
    if len(req.resume_text) > 200_000 or len(req.job_description) > 50_000:
        raise HTTPException(status_code=413, detail="Input too large")
    score = scorer.score_job(req.resume_text, req.job_description, req.job_title)
    matched, missing = scorer.get_skill_gaps(req.resume_text, req.job_description)
    analytics.track("api_score")
    return {
        "score": score,
        "matched_skills": matched[:20],
        "missing_skills": missing[:10],
    }


# ── Vector Job Search ─────────────────────────────────────────────

@app.post("/jobs/search", dependencies=[Depends(_check_key)])
def search_jobs(req: SearchRequest):
    """Semantic job search over indexed job corpus."""
    results = vs.search_jobs(req.query, n_results=req.n_results)
    return {"results": results, "count": len(results)}

@app.post("/jobs/index", dependencies=[Depends(_check_key)])
def index_job(req: IndexJobRequest):
    """Add or update a job in the vector store."""
    vs.index_job(req.job_id, req.title, req.company,
                 req.description, req.source, req.location)
    return {"indexed": True, "job_id": req.job_id}


# ── Metrics (Prometheus-compatible) ──────────────────────────────

@app.get("/metrics")
def metrics():
    """
    Platform metrics in Prometheus text format.
    Public endpoint — no API key required (values are counts, no PII).
    """
    from datetime import datetime as _dt
    import time as _time

    lines = [f"# CareerIQ Metrics — {_dt.utcnow().isoformat()}Z"]

    # Application pipeline counts
    try:
        from collections import Counter as _Counter
        apps  = tracker.get_all()
        counts = _Counter(a.get("status", "unknown") for a in apps)
        for status, count in counts.items():
            lines.append(f'careeriq_applications_total{{status="{status}"}} {count}')
        lines.append(f"careeriq_applications_total_all {len(apps)}")
    except Exception:
        pass

    # Analytics event counts
    try:
        stats = analytics.get_stats()
        for key, val in stats.items():
            lines.append(f"careeriq_event_{key}_total {val}")
    except Exception:
        pass

    # Vector store job count
    try:
        vs_stats = vs.store_stats()
        lines.append(f"careeriq_jobs_indexed {vs_stats.get('jobs_indexed', 0)}")
    except Exception:
        pass

    # Eval engine quality summary
    try:
        from eval_engine import get_eval_summary
        ev_sum = get_eval_summary()
        lines.append(f"careeriq_eval_outputs_total {ev_sum.get('total', 0)}")
        lines.append(f"careeriq_eval_avg_quality {ev_sum.get('avg_overall', 0)}")
    except Exception:
        pass

    # A/B test counts
    try:
        from ab_testing import compute_stats
        ab = compute_stats()
        total_ab_apps = sum(s.get("apps", 0) for s in ab)
        lines.append(f"careeriq_ab_versions_total {len(ab)}")
        lines.append(f"careeriq_ab_applications_total {total_ab_apps}")
    except Exception:
        pass

    lines.append(f"careeriq_api_uptime_ts {int(_time.time())}")

    return "\n".join(lines)

@app.get("/jobs/similar/{job_id}", dependencies=[Depends(_check_key)])
def similar_jobs(job_id: str, n: int = 5):
    """Find jobs similar to a given job."""
    results = vs.get_similar_jobs(job_id, n_results=n)
    return {"results": results, "count": len(results)}


# ── Applications ──────────────────────────────────────────────────

@app.get("/applications", dependencies=[Depends(_check_key)])
def get_applications():
    """Return all tracked job applications."""
    return {"applications": tracker.get_all()}


# ── Analytics ─────────────────────────────────────────────────────

@app.get("/analytics/stats", dependencies=[Depends(_check_key)])
def get_stats():
    """Return platform usage statistics."""
    stats = analytics.get_stats()
    vector_stats = vs.store_stats()
    return {**stats, **vector_stats}

@app.get("/analytics/events", dependencies=[Depends(_check_key)])
def get_events(limit: int = 50):
    """Return recent analytics events."""
    return {"events": analytics.get_recent_events(limit)}


if __name__ == "__main__":
    import uvicorn
    _dev = os.getenv("ENV", "production").lower() == "development"
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=_dev)
