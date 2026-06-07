"""
api.py — CareerIQ REST API
--------------------------
FastAPI layer exposing resume scoring, job matching, and analytics.
Run standalone: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import threading
import time
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import analytics
import auth as _auth
import scorer
import tracker
import vector_store as vs

app = FastAPI(
    title="CareerIQ API",
    description="Resume scoring, job matching, and career analytics",
    version="1.0.0",
)

_DEFAULT_ORIGINS = (
    "http://localhost:8501,https://*.hf.space,https://*.up.railway.app,https://*.streamlit.app"
)
_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"
    return response


_API_KEY = os.getenv("CAREERIQ_API_KEY", "")

# ── Rate limiter (60 req/min per IP) ─────────────────────────────
_rl_lock = threading.Lock()
_rl_counts: dict = defaultdict(lambda: [0, 0.0])  # ip -> [count, window_start]
_RL_LIMIT = int(os.getenv("RATE_LIMIT_RPM", "60"))
_RL_WINDOW = 60.0


def _rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rl_lock:
        # Evict stale windows to prevent unbounded growth under scanner/DDoS traffic
        if len(_rl_counts) > 5000:
            stale = [k for k, (_, ws) in list(_rl_counts.items()) if now - ws >= _RL_WINDOW * 2]
            for k in stale:
                del _rl_counts[k]
        count, window_start = _rl_counts[ip]
        if now - window_start >= _RL_WINDOW:
            _rl_counts[ip] = [1, now]
        else:
            if count >= _RL_LIMIT:
                raise HTTPException(
                    status_code=429, detail="Rate limit exceeded — 60 requests per minute"
                )
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
    job_title: str | None = ""


class SearchRequest(BaseModel):
    query: str
    n_results: int | None = 10
    user_id: str | None = None


class IndexJobRequest(BaseModel):
    job_id: str
    title: str
    company: str
    description: str
    source: str | None = ""
    location: str | None = ""


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
    """
    Liveness + readiness probe.
    Returns per-dependency status so a load balancer or ops team
    can distinguish 'process running' from 'actually ready to serve'.
    """
    import time as _time

    deps: dict = {}

    # Database
    try:
        import db as _db

        conn = _db.connect(
            (Path(__file__).parent / "applications.db") if not _db.IS_POSTGRES else None
        )
        conn.execute("SELECT 1").fetchone()
        conn.close()
        deps["db"] = "ok"
    except Exception as e:
        deps["db"] = f"error: {str(e)[:80]}"

    # Claude API reachability (key configured, not a live call)
    deps["claude_api"] = "ok" if os.getenv("ANTHROPIC_API_KEY") else "unconfigured"

    # Sentence-transformer model
    try:
        from scorer import _model

        deps["embedding_model"] = "loaded" if _model is not None else "not_loaded"
    except Exception:
        deps["embedding_model"] = "unknown"

    # Vector store
    try:
        stats = vs.store_stats()
        deps["vector_store"] = f"ok ({stats.get('jobs_indexed', 0)} jobs)"
    except Exception as e:
        deps["vector_store"] = f"error: {str(e)[:60]}"

    overall = (
        "ok"
        if all(v in ("ok", "loaded", "unconfigured") or v.startswith("ok") for v in deps.values())
        else "degraded"
    )

    return {
        "status": overall,
        "service": "CareerIQ API",
        "version": "1.0.0",
        "uptime_ts": int(_time.time()),
        "deps": deps,
    }


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


@app.post("/score", dependencies=[Depends(_check_key), Depends(_rate_limit)])
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


@app.post("/jobs/search", dependencies=[Depends(_check_key), Depends(_rate_limit)])
def search_jobs(req: SearchRequest):
    """Semantic job search over indexed job corpus."""
    results = vs.search_jobs(req.query, n_results=req.n_results, user_id=req.user_id)
    return {"results": results, "count": len(results)}


@app.post("/jobs/index", dependencies=[Depends(_check_key)])
def index_job(req: IndexJobRequest):
    """Add or update a job in the vector store."""
    vs.index_job(req.job_id, req.title, req.company, req.description, req.source, req.location)
    return {"indexed": True, "job_id": req.job_id}


# ── Metrics (Prometheus-compatible) ──────────────────────────────


@app.get("/metrics", dependencies=[Depends(_check_key)])
def metrics():
    """Platform metrics in Prometheus text format. Requires API key."""
    import time as _time
    from datetime import datetime as _dt

    lines = [f"# CareerIQ Metrics — {_dt.utcnow().isoformat()}Z"]

    # Application pipeline counts
    try:
        from collections import Counter as _Counter

        apps = tracker.get_all()
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
