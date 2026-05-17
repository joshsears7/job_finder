"""
Tests for tracker.py — SQLite operations using a temp DB via conftest.tmp_db.
"""
import pytest
from tests.conftest import SAMPLE_JOB


# ── save_job / is_saved / get_all ─────────────────────────────────────────────

class TestSaveAndRead:
    def test_save_new_job(self, tmp_db):
        import tracker as tr
        result = tr.save_job(SAMPLE_JOB, score=78)
        assert result is True

    def test_duplicate_save_returns_false(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        result = tr.save_job(SAMPLE_JOB, score=78)
        assert result is False

    def test_is_saved_after_save(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        assert tr.is_saved(SAMPLE_JOB["id"]) is True

    def test_is_saved_returns_false_before_save(self, tmp_db):
        import tracker as tr
        assert tr.is_saved("nonexistent-job-xyz") is False

    def test_get_all_returns_saved_job(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        apps = tr.get_all()
        assert len(apps) == 1
        assert apps[0]["title"] == SAMPLE_JOB["title"]
        assert apps[0]["score"] == 78

    def test_get_all_empty_db(self, tmp_db):
        import tracker as tr
        assert tr.get_all() == []

    def test_save_with_resume_version(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=80, resume_version="v2-finance")
        apps = tr.get_all()
        assert apps[0]["resume_version"] == "v2-finance"

    def test_save_preserves_salary(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=80)
        apps = tr.get_all()
        assert apps[0]["salary_min"] == SAMPLE_JOB["salary_min"]
        assert apps[0]["salary_max"] == SAMPLE_JOB["salary_max"]


# ── update_status ─────────────────────────────────────────────────────────────

class TestUpdateStatus:
    def test_status_update(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.update_status(app_id, "applied")
        apps = tr.get_all()
        assert apps[0]["status"] == "applied"

    def test_applied_status_sets_date_applied(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.update_status(app_id, "applied")
        apps = tr.get_all()
        assert apps[0]["date_applied"] is not None

    def test_applied_schedules_followup(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.update_status(app_id, "applied")
        due = tr.get_due_followups(user_id=1)
        # Follow-up is due in 7 days; get_due_followups only shows overdue or today
        # so we check get_all_followups instead
        all_fu = tr.get_all_followups(user_id=1)
        assert len(all_fu) >= 1

    def test_notes_update(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.update_status(app_id, "saved", notes="Strong fit — apply this week")
        apps = tr.get_all()
        assert "Strong fit" in (apps[0]["notes"] or "")

    def test_interview_status(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.update_status(app_id, "interview")
        assert tr.get_all()[0]["status"] == "interview"


# ── delete_app ────────────────────────────────────────────────────────────────

class TestDeleteApp:
    def test_delete_removes_job(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.delete_app(app_id)
        assert tr.get_all() == []

    def test_delete_nonexistent_no_crash(self, tmp_db):
        import tracker as tr
        tr.delete_app(99999)  # should not raise

    def test_is_saved_false_after_delete(self, tmp_db):
        import tracker as tr
        tr.save_job(SAMPLE_JOB, score=78)
        app_id = tr.get_all()[0]["id"]
        tr.delete_app(app_id)
        assert tr.is_saved(SAMPLE_JOB["id"]) is False


# ── Contacts / CRM ────────────────────────────────────────────────────────────

class TestContacts:
    def test_save_and_get_contact(self, tmp_db):
        import tracker as tr
        tr.save_contact(
            name="Sarah Johnson",
            company="Goldman Sachs",
            role="VP Finance",
            how_met="LinkedIn",
            email="sarah@gs.com",
            linkedin="linkedin.com/in/sarah",
            status="warm",
            next_action="Send follow-up",
            notes="Met at career fair",
        )
        contacts = tr.get_contacts()
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Sarah Johnson"

    def test_update_contact(self, tmp_db):
        import tracker as tr
        tr.save_contact(
            name="Sarah Johnson", company="GS", role="VP", how_met="",
            email="", linkedin="", status="warm", next_action="", notes="",
        )
        c_id = tr.get_contacts()[0]["id"]
        tr.update_contact(c_id, status="hot", next_action="Ask for intro", notes="Replied!")
        c = tr.get_contacts()[0]
        assert c["status"] == "hot"
        assert "Replied" in c["notes"]

    def test_delete_contact(self, tmp_db):
        import tracker as tr
        tr.save_contact(
            name="Jane", company="Co", role="Eng", how_met="",
            email="", linkedin="", status="cold", next_action="", notes="",
        )
        c_id = tr.get_contacts()[0]["id"]
        tr.delete_contact(c_id)
        assert tr.get_contacts() == []
