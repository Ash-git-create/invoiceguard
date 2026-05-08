import json
import logging
from openai import OpenAI
from pydantic import ValidationError

from .base import (
    log_event, log_token_usage, update_queue_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from .schemas import PatternRecognitionResponse
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    conn = get_connection()

    try:
        check_cost_limit(conn, "pattern_recognition", invoice_id)

        row = conn.execute("SELECT extracted_data, vendor_name FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        if not row or not row["extracted_data"]:
            raise RuntimeError(f"No formatted data for invoice {invoice_id}")

        invoice_data = json.loads(row["extracted_data"])
        formatted = invoice_data.get("data", {})
        vendor_name = row["vendor_name"] or formatted.get("vendor_name", "Unknown")

        history_row = conn.execute(
            "SELECT value FROM operational_memory WHERE category='vendor_history' AND key=? AND status='approved'",
            (vendor_name,),
        ).fetchone()
        pattern_row = conn.execute(
            "SELECT value FROM operational_memory WHERE category='invoice_patterns' AND key=? AND status='approved'",
            (f"{vendor_name}_pattern",),
        ).fetchone()

        vendor_history = json.loads(history_row["value"]) if history_row else {}
        invoice_patterns = json.loads(pattern_row["value"]) if pattern_row else {}

        instr = get_agent_instructions(conn, "pattern_recognition")
        system_prompt = (
            f"{instr['role_description']}\n"
            f"Methodology: {instr['decision_methodology']}\n\n"
            "Return ONLY valid JSON, no preamble:\n"
            '{"pattern_insights": string, "trend_analysis": string, "recommendations": [string], '
            '"price_change_pct": number, "new_line_items": [string], "removed_line_items": [string], '
            '"reliability_score": number, "flags": [{"reason": string, "severity": "info"|"warning"|"critical"}]}'
        )

        user_prompt = (
            f"Current invoice:\n{json.dumps(formatted)}\n\n"
            f"Vendor history:\n{json.dumps(vendor_history)}\n\n"
            f"Invoice patterns:\n{json.dumps(invoice_patterns)}\n\n"
            "Compare current invoice against historical data. Identify significant changes."
        )

        update_queue_status(conn, queue_id, "processing")

        content, pt, ct = call_openai_with_retry(client, "pattern_recognition", MODEL, system_prompt, user_prompt)

        try:
            validated = PatternRecognitionResponse.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuntimeError(f"pattern_recognition response validation failed: {e}")
        result = validated.model_dump()

        raw_flags = result["flags"]
        flags = [{"agent": "pattern_recognition", "reason": f["reason"], "severity": f["severity"]} for f in raw_flags]
        event_status = "flagged" if flags else "success"

        with conn:
            log_token_usage(conn, "pattern_recognition", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "pattern_recognition", "pattern_recognition_complete",
                result["pattern_insights"],
                {"vendor_name": vendor_name, "history_available": bool(vendor_history)},
                result,
                event_status,
            )
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[pattern_recognition] Invoice {invoice_id}: {len(flags)} pattern flags.")
        return {"status": "success", "invoice_id": invoice_id, "flags": flags, "insights": result}

    except Exception as e:
        logger.error(f"[pattern_recognition] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(conn, invoice_id, "pattern_recognition", "pattern_recognition_failed", str(e), {}, {}, "failure")
            update_queue_status(conn, queue_id, "failed")
        raise
