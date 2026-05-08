import json
import logging
from datetime import datetime, timezone
from openai import OpenAI
from pydantic import ValidationError

from .base import (
    log_event, log_token_usage, update_queue_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from .schemas import AnomalyCheckResponse
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    conn = get_connection()

    try:
        check_cost_limit(conn, "anomaly_check", invoice_id)

        row = conn.execute("SELECT extracted_data FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        if not row or not row["extracted_data"]:
            raise RuntimeError(f"No formatted data for invoice {invoice_id}")

        invoice_data = json.loads(row["extracted_data"])
        formatted = invoice_data.get("data", {})

        rules_rows = conn.execute(
            "SELECT key, value FROM system_knowledge WHERE category='anomaly_rules'"
        ).fetchall()
        anomaly_rules = {r["key"]: json.loads(r["value"]) for r in rules_rows}

        instr = get_agent_instructions(conn, "anomaly_check")
        system_prompt = (
            f"{instr['role_description']}\n"
            f"Methodology: {instr['decision_methodology']}\n\n"
            "Return ONLY valid JSON, no preamble:\n"
            '{"anomalies": [{"type": string, "description": string, "severity": "info"|"warning"|"critical", "reasoning": string}], "summary": string}'
        )

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        user_prompt = (
            f"Invoice data: {json.dumps(formatted)}\n\n"
            f"Anomaly rules: {json.dumps(anomaly_rules)}\n"
            f"Today's date: {today_str}\n\n"
            "Check: duplicate line items, high amounts, round number bias on grand_total, "
            "missing required fields (vendor_name, invoice_date, grand_total), "
            "invoice_date in future beyond threshold, currency consistency."
        )

        update_queue_status(conn, queue_id, "processing")

        content, pt, ct = call_openai_with_retry(client, "anomaly_check", MODEL, system_prompt, user_prompt)

        try:
            validated = AnomalyCheckResponse.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuntimeError(f"anomaly_check response validation failed: {e}")
        result = validated.model_dump()

        anomalies = result["anomalies"]
        flags = [
            {"agent": "anomaly_check", "reason": a["description"], "severity": a["severity"], "type": a["type"]}
            for a in anomalies
        ]

        event_status = "flagged" if flags else "success"

        with conn:
            log_token_usage(conn, "anomaly_check", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "anomaly_check", "anomaly_check_complete",
                result["summary"],
                {"grand_total": formatted.get("grand_total"), "invoice_date": formatted.get("invoice_date")},
                {"anomalies": anomalies, "flags": flags},
                event_status,
            )
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[anomaly_check] Invoice {invoice_id}: {len(anomalies)} anomalies.")
        return {"status": "success", "invoice_id": invoice_id, "flags": flags}

    except Exception as e:
        logger.error(f"[anomaly_check] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(conn, invoice_id, "anomaly_check", "anomaly_check_failed", str(e), {}, {}, "failure")
            update_queue_status(conn, queue_id, "failed")
        raise
