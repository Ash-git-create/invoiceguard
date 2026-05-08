"""Tests for invoice API endpoints."""
import json
import io
import os
import tempfile
import pytest
from unittest.mock import patch


@pytest.fixture
def app_client(tmp_path):
    """Isolated Flask test client: patches DB_PATH at the module level so
    the thread-local connection uses a fresh temp file."""
    db_path = str(tmp_path / "test.db")
    upload_dir = str(tmp_path / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    import invoice_processor.backend.database.connection as conn_mod

    # Swap the module-level path and clear any cached connection
    original_db_path = conn_mod.DB_PATH
    conn_mod.DB_PATH = db_path
    if hasattr(conn_mod._local, "conn") and conn_mod._local.conn:
        conn_mod._local.conn.close()
        conn_mod._local.conn = None

    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    prev_upload = os.environ.get("UPLOAD_DIR")
    os.environ["UPLOAD_DIR"] = upload_dir

    from invoice_processor.backend.main import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False

    with app.test_client() as client:
        yield client

    # Restore
    conn_mod.DB_PATH = original_db_path
    if hasattr(conn_mod._local, "conn") and conn_mod._local.conn:
        conn_mod._local.conn.close()
        conn_mod._local.conn = None
    if prev_upload is None:
        os.environ.pop("UPLOAD_DIR", None)
    else:
        os.environ["UPLOAD_DIR"] = prev_upload


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_client):
        resp = app_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "InvoiceGuard"


class TestInvoiceList:
    def test_empty_list(self, app_client):
        resp = app_client.get("/api/invoices")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_after_upload(self, app_client):
        with patch("invoice_processor.backend.agents.orchestrator.process_invoice"):
            file_data = io.BytesIO(b"Invoice content: $100")
            resp = app_client.post(
                "/api/invoices/upload",
                data={"file": (file_data, "test.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 202

        list_resp = app_client.get("/api/invoices")
        assert list_resp.status_code == 200
        invoices = list_resp.get_json()
        assert len(invoices) == 1
        assert invoices[0]["current_status"] == "received"


class TestInvoiceUpload:
    def test_upload_txt_accepted(self, app_client):
        with patch("invoice_processor.backend.agents.orchestrator.process_invoice"):
            file_data = io.BytesIO(b"Invoice #001\nTotal: $500")
            resp = app_client.post(
                "/api/invoices/upload",
                data={"file": (file_data, "invoice.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert "invoice_id" in data
        assert data["status"] == "received"

    def test_upload_no_file_returns_400(self, app_client):
        resp = app_client.post("/api/invoices/upload", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_unsupported_extension_returns_400(self, app_client):
        file_data = io.BytesIO(b"content")
        resp = app_client.post(
            "/api/invoices/upload",
            data={"file": (file_data, "invoice.exe")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.get_json()["error"]


class TestInvoiceDetail:
    def test_not_found_returns_404(self, app_client):
        resp = app_client.get("/api/invoices/nonexistent-id")
        assert resp.status_code == 404

    def test_detail_after_upload(self, app_client):
        with patch("invoice_processor.backend.agents.orchestrator.process_invoice"):
            file_data = io.BytesIO(b"Invoice content")
            upload_resp = app_client.post(
                "/api/invoices/upload",
                data={"file": (file_data, "inv.txt")},
                content_type="multipart/form-data",
            )
        invoice_id = upload_resp.get_json()["invoice_id"]

        detail_resp = app_client.get(f"/api/invoices/{invoice_id}")
        assert detail_resp.status_code == 200
        data = detail_resp.get_json()
        assert data["invoice_id"] == invoice_id
        assert "events" in data
        assert "final_output" in data


class TestNotifications:
    def test_pending_notifications_empty(self, app_client):
        resp = app_client.get("/api/notifications/pending")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_all_notifications_empty(self, app_client):
        resp = app_client.get("/api/notifications")
        assert resp.status_code == 200


class TestMemoryEndpoints:
    def test_pending_memory_empty(self, app_client):
        resp = app_client.get("/api/memory/pending")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_system_knowledge_seeded(self, app_client):
        resp = app_client.get("/api/memory/system-knowledge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) > 0
        categories = {item["category"] for item in data}
        assert "approved_services" in categories
        assert "approved_vendors" in categories


class TestFeedbackLoop:
    """Tests for item 17 - human override feedback loop."""

    def _setup_invoice_with_verdict(self, app_client, verdict="rejected"):
        """Helper: create invoice + final_output with given verdict."""
        with patch("invoice_processor.backend.agents.orchestrator.process_invoice"):
            file_data = io.BytesIO(b"Invoice content")
            resp = app_client.post(
                "/api/invoices/upload",
                data={"file": (file_data, "inv.txt")},
                content_type="multipart/form-data",
            )
        invoice_id = resp.get_json()["invoice_id"]

        # Use API to get invoice, then directly update via a second request
        # We can do the DB write through the app's own connection (DB_PATH is patched)
        import invoice_processor.backend.database.connection as conn_mod
        conn = conn_mod.get_connection()
        conn.execute(
            "UPDATE invoices SET vendor_name=?, current_status='flagged' WHERE invoice_id=?",
            ("TestVendor", invoice_id),
        )
        import uuid
        conn.execute(
            """INSERT INTO final_output
               (output_id, invoice_id, verdict, summary, flags, recommendations, pattern_insights, created_at)
               VALUES (?,?,?,?,?,?,?,datetime('now'))""",
            (str(uuid.uuid4()), invoice_id, verdict, "Test verdict",
             json.dumps([{"agent": "service_check", "reason": "Unknown service", "severity": "critical"}]),
             json.dumps([]), ""),
        )
        conn.commit()
        return invoice_id

    def test_approve_flag_creates_memory_entry(self, app_client):
        invoice_id = self._setup_invoice_with_verdict(app_client)

        resp = app_client.post(
            f"/api/invoices/{invoice_id}/approve-flag",
            json={"performed_by": "admin", "reasoning": "Vendor is trusted partner"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        import invoice_processor.backend.database.connection as conn_mod
        conn = conn_mod.get_connection()
        rows = conn.execute(
            "SELECT * FROM operational_memory WHERE category='flag_history' AND key LIKE '%approved_override%'"
        ).fetchall()
        assert len(rows) >= 1
        value = json.loads(rows[0]["value"])
        assert value["human_action"] == "approved_override"
        assert value["vendor"] == "TestVendor"

    def test_reject_flag_creates_memory_entry(self, app_client):
        invoice_id = self._setup_invoice_with_verdict(app_client)

        resp = app_client.post(
            f"/api/invoices/{invoice_id}/reject-flag",
            json={"performed_by": "admin", "reasoning": "Confirmed bad invoice"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        import invoice_processor.backend.database.connection as conn_mod
        conn = conn_mod.get_connection()
        rows = conn.execute(
            "SELECT * FROM operational_memory WHERE category='flag_history' AND key LIKE '%confirmed_rejection%'"
        ).fetchall()
        assert len(rows) >= 1
        value = json.loads(rows[0]["value"])
        assert value["human_action"] == "confirmed_rejection"
