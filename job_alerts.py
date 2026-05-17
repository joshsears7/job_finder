"""
job_alerts.py
-------------
Save job alert configs and send ntfy push notifications when
new matching jobs appear above a fit-score threshold.

Cron setup (add to crontab):
    0 8 * * 1-5 cd /Users/joshuasears/Downloads/job_finder && python job_alerts.py >> alerts.log 2>&1

Manual run:
    python job_alerts.py
"""

import json
import os
import requests
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_alerts_config.json")


# ── Config helpers ────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        "alerts":      [],
        "ntfy_topic":  "",
        "resume_text": "",
        "seen_ids":    [],
        "last_run":    None,
    }


def save_config(config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def add_alert(role: str, cities: list, min_score: int = 60):
    config = load_config()
    # Remove duplicate
    config["alerts"] = [a for a in config["alerts"]
                        if not (a["role"] == role and a["cities"] == cities)]
    config["alerts"].append({"role": role, "cities": cities, "min_score": min_score})
    save_config(config)


def remove_alert(role: str, cities: list):
    config = load_config()
    config["alerts"] = [a for a in config["alerts"]
                        if not (a["role"] == role and a["cities"] == cities)]
    save_config(config)


def set_ntfy_topic(topic: str):
    config = load_config()
    config["ntfy_topic"] = topic
    save_config(config)


def set_resume_text(text: str):
    config = load_config()
    config["resume_text"] = text
    save_config(config)


# ── ntfy sender ───────────────────────────────────────────────────

def send_ntfy(topic: str, title: str, body: str, url: str = "") -> bool:
    if not topic:
        return False
    try:
        headers = {
            "Title":    title,
            "Priority": "default",
            "Tags":     "briefcase",
        }
        if url:
            headers["Click"] = url
        r = requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=8,
        )
        return r.status_code < 300
    except Exception:
        return False


def test_ntfy(topic: str) -> bool:
    """Send a test notification to verify setup."""
    return send_ntfy(
        topic,
        "CareerIQ Alerts — Connected!",
        "Job alerts are set up. You'll get notified when new matching jobs appear.",
    )


# ── Main runner ───────────────────────────────────────────────────

def run_alerts() -> dict:
    """
    Fetch jobs for each saved alert, score them, and push
    ntfy notifications for new jobs above threshold.
    Returns summary dict.
    """
    from job_fetcher import fetch_jobs_multicity
    from scorer import score_job

    config = load_config()
    topic       = config.get("ntfy_topic", "")
    resume_text = config.get("resume_text", "")
    alerts      = config.get("alerts", [])
    seen_ids    = set(config.get("seen_ids", []))

    if not alerts:
        return {"sent": 0, "checked": 0, "error": "No alerts configured."}
    if not topic:
        return {"sent": 0, "checked": 0, "error": "No ntfy topic set."}

    sent    = 0
    checked = 0

    for alert in alerts:
        role      = alert.get("role", "")
        cities    = alert.get("cities", [])
        min_score = alert.get("min_score", 60)
        if not role or not cities:
            continue

        jobs = fetch_jobs_multicity(role, cities, num_per_city=8)
        for j in jobs:
            checked += 1
            jid = j["id"]
            if jid in seen_ids:
                continue
            seen_ids.add(jid)

            score = score_job(resume_text, j["description"]) if resume_text else 0
            if score >= min_score or not resume_text:
                sal = ""
                if j.get("salary_min") and j.get("salary_max"):
                    sal = f"\n💰 ${int(j['salary_min']):,}–${int(j['salary_max']):,}"
                body = (
                    f"{j['company']} · {j['location']}\n"
                    f"📊 Fit: {score}%  ·  {j['source']}{sal}\n"
                    f"{j.get('description','')[:120]}…"
                )
                ok = send_ntfy(topic, f"New: {j['title']} @ {j['company']}", body, j.get("url",""))
                if ok:
                    sent += 1

    # Persist seen IDs (keep last 3000)
    config["seen_ids"]  = list(seen_ids)[-3000:]
    config["last_run"]  = datetime.now().isoformat()
    save_config(config)

    return {"sent": sent, "checked": checked, "error": None}


# ── Cron entrypoint ───────────────────────────────────────────────

if __name__ == "__main__":
    result = run_alerts()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if result["error"]:
        print(f"[{ts}] ERROR: {result['error']}")
    else:
        print(f"[{ts}] Checked {result['checked']} jobs · Sent {result['sent']} alerts")
