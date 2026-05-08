import sys
import os
import json
import sqlite3
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invoice_processor.backend.database.schema import SCHEMA_SQL


@pytest.fixture
def db():
    """In-memory SQLite with full schema (no seed data needed for unit tests)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def invoice_id(db):
    """Insert a minimal invoice record and return its id."""
    iid = "test-invoice-0001"
    db.execute(
        "INSERT INTO invoices (invoice_id, raw_file_path, current_status, created_at, updated_at) VALUES (?,?,?,datetime('now'),datetime('now'))",
        (iid, "/tmp/test.txt", "received"),
    )
    db.commit()
    return iid


@pytest.fixture
def formatted_invoice_id(db, invoice_id):
    """Advance the invoice to formatted state with sample data."""
    sample = {
        "stage": "formatted",
        "data": {
            "vendor_name": "TechSolutions Inc.",
            "vendor_id": "TECH001",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-01",
            "due_date": "2026-05-31",
            "line_items": [
                {"description": "CRM Software License", "quantity": 1, "unit_price": 150.0, "total": 150.0}
            ],
            "subtotal": 150.0,
            "tax": 15.0,
            "grand_total": 165.0,
            "currency": "USD",
            "payment_terms": "Net 30",
            "math_valid": True,
            "math_notes": "Math checks passed",
        },
        "flags": [],
    }
    db.execute(
        "UPDATE invoices SET extracted_data=?, vendor_name=?, current_status='formatting' WHERE invoice_id=?",
        (json.dumps(sample), "TechSolutions Inc.", invoice_id),
    )
    db.commit()
    return invoice_id


@pytest.fixture
def mock_openai_client():
    """OpenAI client that returns a valid JSON response."""
    client = MagicMock()

    def make_response(content):
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = content
        resp.usage.prompt_tokens = 100
        resp.usage.completion_tokens = 50
        return resp

    client._make_response = make_response
    return client


@pytest.fixture
def flask_app():
    """Flask test client with test configuration."""
    import tempfile
    import os

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.environ["DB_PATH"] = db_path
    os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
    os.environ["OPENAI_API_KEY"] = "sk-test-key"

    from invoice_processor.backend.main import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False

    with app.test_client() as client:
        yield client

    os.close(db_fd)
    os.unlink(db_path)
