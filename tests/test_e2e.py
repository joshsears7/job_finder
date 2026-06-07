"""
tests/test_e2e.py
-----------------
End-to-end browser tests via Playwright.
Marked 'slow' — excluded from the default 'pytest -m "not slow"' run.
Run explicitly: pytest tests/test_e2e.py -v --timeout=120
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

try:
    from playwright.sync_api import sync_playwright

    _PW_AVAILABLE = True
except ImportError:
    _PW_AVAILABLE = False

pytestmark = pytest.mark.slow

_APP_DIR = Path(__file__).parent.parent
_APP_URL = os.getenv("APP_URL", "http://localhost:8501")
_HEALTH = f"{_APP_URL}/_stcore/health"
_NAV_OPTS = {"timeout": 30_000, "wait_until": "networkidle"}


def _server_up(url: str, tries: int = 3) -> bool:
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


@pytest.fixture(scope="module")
def app_url():
    if not _PW_AVAILABLE:
        pytest.skip("playwright not installed")

    already_up = _server_up(_HEALTH)
    proc = None

    if not already_up:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.port=8501",
                "--server.headless=true",
                "--server.runOnSave=false",
                "--browser.gatherUsageStats=false",
            ],
            cwd=str(_APP_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait up to 90s for the server to be ready
        ready = False
        for _ in range(90):
            if _server_up(_HEALTH, tries=1):
                ready = True
                break
            time.sleep(1)
        if not ready:
            proc.terminate()
            pytest.fail("Streamlit server did not start within 90s")
        # Extra settle time for the app's own startup (model imports etc.)
        time.sleep(3)

    yield _APP_URL

    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


class TestAuthGate:
    """Tests for the pre-login landing page."""

    def test_page_title_contains_careeriq(self, app_url):
        """Browser tab title should include CareerIQ."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)
            assert "CareerIQ" in page.title()
            browser.close()

    def test_try_demo_button_is_visible(self, app_url):
        """'Try Live Demo' button is present before login."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)
            btn = page.get_by_role("button", name="Try Live Demo")
            btn.wait_for(timeout=15_000)
            assert btn.is_visible()
            browser.close()

    def test_sign_in_tab_is_present(self, app_url):
        """Sign In tab exists in the auth widget."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)
            tab = page.get_by_role("tab", name="Sign In")
            tab.wait_for(timeout=15_000)
            assert tab.is_visible()
            browser.close()

    def test_create_account_tab_is_present(self, app_url):
        """Create Account tab exists in the auth widget."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)
            tab = page.get_by_role("tab", name="Create Account")
            tab.wait_for(timeout=15_000)
            assert tab.is_visible()
            browser.close()


class TestDemoFlow:
    """Tests for the one-click demo user flow.

    Streamlit communicates via WebSocket — page reruns are not tracked by
    Playwright's network-idle detector. We use wait_for_function() to poll
    the DOM until post-login content appears.
    """

    # Content that only appears in the dashboard (not on the auth gate)
    _POST_LOGIN_JS = """() => {
        const t = document.body.innerText;
        return (
            t.includes('100% Free') ||
            t.includes('Resume Health') ||
            t.includes('Try Demo Resume') ||
            t.includes('Upload your resume') ||
            t.includes('How it works')
        );
    }"""

    def test_demo_login_shows_dashboard_content(self, app_url):
        """Clicking 'Try Live Demo' renders the post-login dashboard."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)

            page.get_by_role("button", name="Try Live Demo").click()
            # Poll DOM — WebSocket rerun isn't captured by networkidle
            page.wait_for_function(self._POST_LOGIN_JS, timeout=30_000)

            body = page.locator("body").text_content()
            assert any(
                phrase in body
                for phrase in [
                    "100% Free",
                    "Resume Health",
                    "Try Demo Resume",
                    "Upload your resume",
                    "How it works",
                ]
            ), "Expected post-login dashboard content"
            browser.close()

    def test_demo_login_hides_auth_form(self, app_url):
        """After demo login the Sign In form is no longer the primary content."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)

            # Confirm auth form is present before clicking
            assert page.get_by_role("tab", name="Sign In").count() > 0

            page.get_by_role("button", name="Try Live Demo").click()
            page.wait_for_function(self._POST_LOGIN_JS, timeout=30_000)

            # The auth-gate Sign In tab should be gone after login
            assert page.get_by_role("tab", name="Sign In").count() == 0
            browser.close()

    def test_demo_login_shows_resume_section(self, app_url):
        """Dashboard shows resume-related content after demo login."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(app_url, **_NAV_OPTS)

            page.get_by_role("button", name="Try Live Demo").click()
            page.wait_for_function(self._POST_LOGIN_JS, timeout=30_000)

            has_resume_ui = (
                page.locator("text=Upload your resume").count() > 0
                or page.locator("text=Resume Score").count() > 0
                or page.locator("text=Resume Health").count() > 0
                or page.locator("text=Try Demo Resume").count() > 0
                or page.locator("text=100% Free").count() > 0
            )
            assert has_resume_ui, "Expected resume UI after demo login"
            browser.close()


class TestHealthEndpoints:
    """Non-browser health checks that run alongside e2e tests."""

    def test_streamlit_health_ok(self, app_url):
        """/_stcore/health returns a 200."""
        resp = urllib.request.urlopen(f"{app_url}/_stcore/health", timeout=5)
        assert resp.status == 200

    def test_streamlit_health_body(self, app_url):
        """/_stcore/health body indicates ok."""
        resp = urllib.request.urlopen(f"{app_url}/_stcore/health", timeout=5)
        body = resp.read().decode().lower()
        assert "ok" in body


class TestVectorStoreIsolation:
    """Unit tests for per-user job scoping in vector_store."""

    def test_global_job_appears_in_unfiltered_search(self, tmp_path, monkeypatch):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        import vector_store as vs

        # Redirect to a temp chroma dir so we don't pollute production data
        tmp_db = tmp_path / "chroma_test"
        tmp_db.mkdir()
        _ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        _c = chromadb.PersistentClient(path=str(tmp_db))
        _col = _c.get_or_create_collection(
            name="jobs_test", embedding_function=_ef, metadata={"hnsw:space": "cosine"}
        )
        monkeypatch.setattr(vs, "_jobs_col", _col)

        vs.index_job(
            "g1",
            "Python Engineer",
            "GlobalCo",
            "Python backend engineer with FastAPI and PostgreSQL experience",
            user_id="global",
        )

        results = vs.search_jobs("Python backend engineer", n_results=5)
        assert len(results) > 0
        assert results[0]["job_id"] == "g1"

    def test_user_job_isolated_from_other_user(self, tmp_path, monkeypatch):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        import vector_store as vs

        tmp_db = tmp_path / "chroma_iso"
        tmp_db.mkdir()
        _ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        _c = chromadb.PersistentClient(path=str(tmp_db))
        _col = _c.get_or_create_collection(
            name="jobs_iso", embedding_function=_ef, metadata={"hnsw:space": "cosine"}
        )
        monkeypatch.setattr(vs, "_jobs_col", _col)

        # user 42 indexes a private job
        vs.index_job(
            "u42j1",
            "Nurse Practitioner",
            "HealthCo",
            "Registered nurse with ICU experience and NCLEX license required",
            user_id="42",
        )

        # user 99 searches — should NOT see user 42's private job
        results = vs.search_jobs("nurse ICU NCLEX", n_results=5, user_id="99")
        ids = [r["job_id"] for r in results]
        assert "u42j1" not in ids

    def test_global_job_visible_to_all_users(self, tmp_path, monkeypatch):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        import vector_store as vs

        tmp_db = tmp_path / "chroma_global"
        tmp_db.mkdir()
        _ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        _c = chromadb.PersistentClient(path=str(tmp_db))
        _col = _c.get_or_create_collection(
            name="jobs_global", embedding_function=_ef, metadata={"hnsw:space": "cosine"}
        )
        monkeypatch.setattr(vs, "_jobs_col", _col)

        vs.index_job(
            "pub1",
            "Data Analyst",
            "OpenCo",
            "Data analyst role using Python, SQL, and Tableau",
            user_id="global",
        )

        # Any user should see the global job
        for uid in ("1", "42", "99"):
            results = vs.search_jobs("Python SQL analyst", n_results=5, user_id=uid)
            ids = [r["job_id"] for r in results]
            assert "pub1" in ids, f"user {uid} should see global job"
