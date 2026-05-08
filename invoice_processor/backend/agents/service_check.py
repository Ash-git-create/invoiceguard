import json
import logging
from openai import OpenAI
from pydantic import ValidationError

from .base import (
    log_event, log_token_usage, update_queue_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from .schemas import ServiceCheckResponse
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    conn = get_connection()

    try:
        check_cost_limit(conn, "service_check", invoice_id)

        row = conn.execute("SELECT extracted_data FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        if not row or not row["extracted_data"]:
            raise RuntimeError(f"No formatted data for invoice {invoice_id}")

        invoice_data = json.loads(row["extracted_data"])
        formatted = invoice_data.get("data", {})
        line_items = formatted.get("line_items", [])

        services_rows = conn.execute(
            "SELECT key, value FROM system_knowledge WHERE category='approved_services'"
        ).fetchall()
        approved_services = {r["key"]: json.loads(r["value"]) for r in services_rows}

        vendors_rows = conn.execute(
            "SELECT key, value FROM system_knowledge WHERE category='approved_vendors'"
        ).fetchall()
        approved_vendors = {r["key"]: json.loads(r["value"]) for r in vendors_rows}

        instr = get_agent_instructions(conn, "service_check")
        system_prompt = (
            f"{instr['role_description']}\n"
            f"Methodology: {instr['decision_methodology']}\n\n"
            "Return ONLY valid JSON, no preamble:\n"
            '{"verdicts": [{"description": string, "approved": boolean, "reason": string, "severity": "info"|"warning"|"critical"}], '
            '"vendor_approved": boolean, "vendor_reason": string, "summary": string}'
        )

        user_prompt = (
            f"Vendor: {formatted.get('vendor_name', 'Unknown')}\n"
            f"Line items: {json.dumps(line_items)}\n\n"
            f"Approved services catalog: {json.dumps(approved_services)}\n"
            f"Approved vendors: {json.dumps({k: v['name'] for k, v in approved_vendors.items()})}"
        )

        update_queue_status(conn, queue_id, "processing")

        content, pt, ct = call_openai_with_retry(client, "service_check", MODEL, system_prompt, user_prompt)

        try:
            validated = ServiceCheckResponse.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuntimeError(f"service_check response validation failed: {e}")
        result = validated.model_dump()

        flags = []
        verdicts = result["verdicts"]
        for v in verdicts:
            if not v["approved"]:
                flags.append({"agent": "service_check", "reason": v["reason"], "severity": v["severity"], "item": v["description"]})

        if not result["vendor_approved"]:
            flags.append({"agent": "service_check", "reason": result["vendor_reason"] or "Vendor not approved", "severity": "critical", "item": "vendor"})

        event_status = "flagged" if flags else "success"

        with conn:
            log_token_usage(conn, "service_check", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "service_check", "service_check_complete",
                result.get("summary", ""),
                {"line_items": line_items, "vendor": formatted.get("vendor_name")},
                {"verdicts": verdicts, "flags": flags},
                event_status,
            )
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[service_check] Invoice {invoice_id}: {len(flags)} flags.")
        return {"status": "success", "invoice_id": invoice_id, "flags": flags}

    except Exception as e:
        logger.error(f"[service_check] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(conn, invoice_id, "service_check", "service_check_failed", str(e), {}, {}, "failure")
            update_queue_status(conn, queue_id, "failed")
        raise
