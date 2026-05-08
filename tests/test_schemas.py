"""Tests for Pydantic agent response schemas (item 4)."""
import pytest
from pydantic import ValidationError

from invoice_processor.backend.agents.schemas import (
    FormatterResponse,
    ServiceCheckResponse,
    AnomalyCheckResponse,
    PatternRecognitionResponse,
    DecisionAgentResponse,
    LineItem,
    ServiceVerdict,
    Anomaly,
)


class TestFormatterResponse:
    def test_valid_full_response(self):
        data = {
            "vendor_name": "Acme Corp",
            "vendor_id": "ACME001",
            "invoice_number": "INV-2026-001",
            "invoice_date": "2026-05-01",
            "due_date": "2026-05-31",
            "line_items": [{"description": "Widget", "quantity": 10, "unit_price": 5.0, "total": 50.0}],
            "subtotal": 50.0,
            "tax": 5.0,
            "grand_total": 55.0,
            "currency": "USD",
            "payment_terms": "Net 30",
            "math_valid": True,
            "math_notes": "Math checks passed",
        }
        r = FormatterResponse.model_validate(data)
        assert r.vendor_name == "Acme Corp"
        assert r.grand_total == 55.0
        assert len(r.line_items) == 1
        assert r.line_items[0].description == "Widget"

    def test_defaults_on_missing_fields(self):
        r = FormatterResponse.model_validate({})
        assert r.vendor_name == ""
        assert r.currency == "USD"
        assert r.math_valid is True
        assert r.line_items == []

    def test_model_dump_produces_dict(self):
        r = FormatterResponse.model_validate({"vendor_name": "Test", "grand_total": 100.0})
        d = r.model_dump()
        assert isinstance(d, dict)
        assert d["vendor_name"] == "Test"
        assert d["grand_total"] == 100.0

    def test_validate_json_parses_string(self):
        import json
        payload = json.dumps({"vendor_name": "JSON Corp", "grand_total": 200.0})
        r = FormatterResponse.model_validate_json(payload)
        assert r.vendor_name == "JSON Corp"

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            FormatterResponse.model_validate_json("not json at all")


class TestServiceCheckResponse:
    def test_approved_verdicts(self):
        data = {
            "verdicts": [{"description": "CRM License", "approved": True, "reason": "In catalog", "severity": "info"}],
            "vendor_approved": True,
            "vendor_reason": "",
            "summary": "All clear",
        }
        r = ServiceCheckResponse.model_validate(data)
        assert r.vendor_approved is True
        assert r.verdicts[0].approved is True

    def test_unapproved_verdict(self):
        data = {
            "verdicts": [{"description": "Mystery Service", "approved": False, "reason": "Not in catalog", "severity": "critical"}],
            "vendor_approved": False,
            "vendor_reason": "Unknown vendor",
            "summary": "Flagged",
        }
        r = ServiceCheckResponse.model_validate(data)
        assert r.verdicts[0].severity == "critical"
        assert not r.vendor_approved

    def test_empty_defaults(self):
        r = ServiceCheckResponse.model_validate({})
        assert r.verdicts == []
        assert r.vendor_approved is True

    def test_invalid_severity_coerces(self):
        # Pydantic Literal will reject unknown values
        with pytest.raises(ValidationError):
            ServiceVerdict.model_validate({"description": "X", "approved": True, "severity": "extreme"})


class TestAnomalyCheckResponse:
    def test_no_anomalies(self):
        r = AnomalyCheckResponse.model_validate({"anomalies": [], "summary": "Clean"})
        assert r.anomalies == []

    def test_anomaly_fields(self):
        data = {
            "anomalies": [{"type": "duplicate", "description": "Dup item", "severity": "warning", "reasoning": "Same desc+price"}],
            "summary": "1 anomaly",
        }
        r = AnomalyCheckResponse.model_validate(data)
        assert r.anomalies[0].type == "duplicate"
        assert r.anomalies[0].severity == "warning"

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            Anomaly.model_validate({"type": "x", "description": "y", "severity": "extreme"})


class TestPatternRecognitionResponse:
    def test_defaults(self):
        r = PatternRecognitionResponse.model_validate({})
        assert r.reliability_score == 1.0
        assert r.flags == []
        assert r.price_change_pct == 0.0

    def test_flags(self):
        data = {"flags": [{"reason": "Price up 50%", "severity": "warning"}]}
        r = PatternRecognitionResponse.model_validate(data)
        assert r.flags[0].severity == "warning"


class TestDecisionAgentResponse:
    def test_valid_approved(self):
        data = {"verdict": "approved", "summary": "All good", "confidence": 0.95}
        r = DecisionAgentResponse.model_validate(data)
        assert r.verdict == "approved"
        assert r.confidence == 0.95

    def test_valid_rejected(self):
        r = DecisionAgentResponse.model_validate({"verdict": "rejected", "summary": "Bad vendor"})
        assert r.verdict == "rejected"

    def test_invalid_verdict_coerced_to_requires_human(self):
        r = DecisionAgentResponse.model_validate({"verdict": "UNKNOWN_VERDICT"})
        assert r.verdict == "requires_human"

    def test_confidence_clamped(self):
        with pytest.raises(ValidationError):
            DecisionAgentResponse.model_validate({"verdict": "approved", "confidence": 1.5})

    def test_flags_default_empty(self):
        r = DecisionAgentResponse.model_validate({"verdict": "flagged"})
        assert r.flags == []
        assert r.recommendations == []
