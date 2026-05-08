"""Tests for base agent utilities (cost tracking, event logging, retry logic)."""
import json
import pytest
from unittest.mock import MagicMock, patch, call
from openai import RateLimitError, APIConnectionError

from invoice_processor.backend.agents.base import (
    get_cumulative_cost,
    check_cost_limit,
    log_token_usage,
    log_event,
    update_invoice_status,
    HARD_COST_LIMIT_USD,
    COST_PER_TOKEN,
    call_openai_with_retry,
)


class TestCostTracking:
    def test_get_cumulative_cost_empty(self, db):
        assert get_cumulative_cost(db) == 0.0

    def test_log_token_usage_calculates_cost(self, db, invoice_id):
        cost = log_token_usage(db, "formatter", invoice_id, "gpt-4o-mini", 1000, 500)
        db.commit()
        assert cost == pytest.approx(1000 * 0.00000015 + 500 * 0.0000006)

    def test_cumulative_cost_sums_entries(self, db, invoice_id):
        log_token_usage(db, "formatter", invoice_id, "gpt-4o-mini", 1000, 500)
        log_token_usage(db, "service_check", invoice_id, "gpt-4o-mini", 2000, 1000)
        db.commit()
        total = get_cumulative_cost(db)
        expected = (1000 + 2000) * 0.00000015 + (500 + 1000) * 0.0000006
        assert total == pytest.approx(expected)

    def test_check_cost_limit_passes_under_limit(self, db, invoice_id):
        # Should not raise when cost is 0
        check_cost_limit(db, "formatter", invoice_id)

    def test_check_cost_limit_raises_at_limit(self, db, invoice_id):
        # Insert enough usage to breach the $1.50 limit
        # gpt-4o: $0.0000025/input, $0.00001/output
        # 100k input tokens × $0.0000025 = $0.25 per call → need 6 calls
        for _ in range(7):
            log_token_usage(db, "decision_agent", invoice_id, "gpt-4o", 100000, 10000)
        db.commit()

        with pytest.raises(RuntimeError, match="COST LIMIT EXCEEDED"):
            check_cost_limit(db, "decision_agent", invoice_id)

    def test_unknown_model_uses_zero_cost(self, db, invoice_id):
        cost = log_token_usage(db, "formatter", invoice_id, "gpt-99-unknown", 1000, 500)
        assert cost == 0.0


class TestEventLogging:
    def test_log_event_inserts_row(self, db, invoice_id):
        log_event(db, invoice_id, "formatter", "formatting_complete",
                  "Formatted OK", {"raw_len": 100}, {"vendor": "Acme"}, "success")
        db.commit()
        row = db.execute("SELECT * FROM event_log WHERE invoice_id=?", (invoice_id,)).fetchone()
        assert row is not None
        assert row["agent_name"] == "formatter"
        assert row["status"] == "success"

    def test_event_log_is_immutable(self, db, invoice_id):
        log_event(db, invoice_id, "formatter", "test_event",
                  "reasoning", {}, {}, "success")
        db.commit()
        row = db.execute("SELECT event_id FROM event_log WHERE invoice_id=?", (invoice_id,)).fetchone()
        with pytest.raises(Exception, match="immutable"):
            db.execute("UPDATE event_log SET status='failure' WHERE event_id=?", (row["event_id"],))
            db.commit()

    def test_event_log_delete_blocked(self, db, invoice_id):
        log_event(db, invoice_id, "formatter", "test_event",
                  "reasoning", {}, {}, "success")
        db.commit()
        with pytest.raises(Exception, match="immutable"):
            db.execute("DELETE FROM event_log WHERE invoice_id=?", (invoice_id,))
            db.commit()


class TestInvoiceStatusUpdate:
    def test_update_status(self, db, invoice_id):
        update_invoice_status(db, invoice_id, "formatting")
        db.commit()
        row = db.execute("SELECT current_status FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        assert row["current_status"] == "formatting"

    def test_update_status_with_vendor(self, db, invoice_id):
        update_invoice_status(db, invoice_id, "completed", vendor_name="Acme Corp")
        db.commit()
        row = db.execute("SELECT current_status, vendor_name FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        assert row["current_status"] == "completed"
        assert row["vendor_name"] == "Acme Corp"


class TestOpenAIRetry:
    def test_success_on_first_attempt(self):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = '{"result": "ok"}'
        resp.usage.prompt_tokens = 10
        resp.usage.completion_tokens = 5
        client.chat.completions.create.return_value = resp

        content, pt, ct = call_openai_with_retry(client, "formatter", "gpt-4o-mini", "sys", "user")
        assert content == '{"result": "ok"}'
        assert pt == 10
        assert ct == 5

    def test_retries_on_rate_limit(self):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = '{"ok": true}'
        resp.usage.prompt_tokens = 10
        resp.usage.completion_tokens = 5

        client.chat.completions.create.side_effect = [
            RateLimitError("rate limited", response=MagicMock(status_code=429), body={}),
            resp,
        ]

        with patch("invoice_processor.backend.agents.base.time.sleep"):
            content, pt, ct = call_openai_with_retry(client, "formatter", "gpt-4o-mini", "sys", "user", max_retries=3)
        assert content == '{"ok": true}'
        assert client.chat.completions.create.call_count == 2

    def test_raises_after_max_retries(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())

        with patch("invoice_processor.backend.agents.base.time.sleep"):
            with pytest.raises(RuntimeError, match="Max retries exceeded"):
                call_openai_with_retry(client, "formatter", "gpt-4o-mini", "sys", "user", max_retries=2)

        assert client.chat.completions.create.call_count == 3
