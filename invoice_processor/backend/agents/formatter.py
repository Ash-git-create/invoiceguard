import json
import uuid
import logging
from openai import OpenAI
from pydantic import ValidationError

from .base import (
    log_event, log_token_usage, update_queue_status, update_invoice_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from .schemas import FormatterResponse
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

SYSTEM_TEMPLATE = """{role_description}
Methodology: {decision_methodology}

Return ONLY valid JSON with this exact schema, no preamble:
{{
  "vendor_name": string,
  "vendor_id": string,
  "invoice_number": string,
  "invoice_date": string (YYYY-MM-DD),
  "due_date": string (YYYY-MM-DD),
  "line_items": [
    {{"description": string, "quantity": number, "unit_price": number, "total": number}}
  ],
  "subtotal": number,
  "tax": number,
  "grand_total": number,
  "currency": string (ISO 4217),
  "payment_terms": string,
  "math_valid": boolean,
  "math_notes": string
}}
"""


def _validate_math(data: dict) -> tuple[bool, str]:
    try:
        line_sum = sum(item.get("total", 0.0) for item in data.get("line_items", []))
        subtotal = data.get("subtotal", 0.0)
        tax = data.get("tax", 0.0)
        grand_total = data.get("grand_total", 0.0)

        notes = []
        valid = True

        if abs(line_sum - subtotal) > 0.02:
            notes.append(f"Line items sum ({line_sum:.2f}) != subtotal ({subtotal:.2f})")
            valid = False
        if abs(subtotal + tax - grand_total) > 0.02:
            notes.append(f"subtotal+tax ({subtotal+tax:.2f}) != grand_total ({grand_total:.2f})")
            valid = False

        return valid, "; ".join(notes) if notes else "Math checks passed"
    except Exception as e:
        return False, f"Math validation error: {e}"


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    conn = get_connection()

    try:
        check_cost_limit(conn, "formatter", invoice_id)

        row = conn.execute("SELECT extracted_data FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        if not row or not row["extracted_data"]:
            raise RuntimeError(f"No extracted data for invoice {invoice_id}")

        extracted = json.loads(row["extracted_data"])
        raw_text = extracted.get("raw_text", "")

        anomaly_rules_rows = conn.execute(
            "SELECT key, value FROM system_knowledge WHERE category='anomaly_rules'"
        ).fetchall()
        anomaly_rules = {r["key"]: json.loads(r["value"]) for r in anomaly_rules_rows}

        instr = get_agent_instructions(conn, "formatter")
        system_prompt = SYSTEM_TEMPLATE.format(
            role_description=instr["role_description"],
            decision_methodology=instr["decision_methodology"],
        )
        user_prompt = f"Raw invoice text to structure:\n\n{raw_text[:3000]}"

        with conn:
            update_invoice_status(conn, invoice_id, "formatting")
            update_queue_status(conn, queue_id, "processing")

        content, pt, ct = call_openai_with_retry(client, "formatter", MODEL, system_prompt, user_prompt)

        try:
            validated = FormatterResponse.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuntimeError(f"Formatter response validation failed: {e}")
        formatted = validated.model_dump()

        math_valid, math_notes = _validate_math(formatted)
        formatted["math_valid"] = math_valid
        formatted["math_notes"] = math_notes

        vendor_name = formatted.get("vendor_name", "Unknown Vendor")
        flags = []
        status = "success"

        if not math_valid:
            flags.append({"agent": "formatter", "reason": math_notes, "severity": "critical"})
            status = "flagged"

        formatted_json = json.dumps({"stage": "formatted", "data": formatted, "flags": flags})

        with conn:
            conn.execute(
                "UPDATE invoices SET extracted_data=?, vendor_name=?, updated_at=? WHERE invoice_id=?",
                (formatted_json, vendor_name, _now(), invoice_id),
            )
            log_token_usage(conn, "formatter", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "formatter", "formatting_complete",
                f"Formatted invoice. Math valid: {math_valid}. Vendor: {vendor_name}",
                {"raw_text_length": len(raw_text)},
                {"formatted": formatted, "flags": flags},
                status,
            )
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[formatter] Invoice {invoice_id} formatted. Math valid: {math_valid}")
        return {"status": "success", "invoice_id": invoice_id, "flags": flags, "vendor_name": vendor_name}

    except Exception as e:
        logger.error(f"[formatter] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(conn, invoice_id, "formatter", "formatting_failed", str(e), {}, {}, "failure")
            update_queue_status(conn, queue_id, "failed")
            update_invoice_status(conn, invoice_id, "failed")
        raise
