import json
import uuid
import logging
from openai import OpenAI

from .base import (
    log_event, log_token_usage, update_queue_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    payload = json.loads(queue_item.get("payload", "{}")) if queue_item.get("payload") else {}
    notification_type = payload.get("notification_type", "summary")
    conn = get_connection()

    try:
        check_cost_limit(conn, "notifier", invoice_id)

        inv_row = conn.execute(
            "SELECT extracted_data, vendor_name, current_status FROM invoices WHERE invoice_id=?",
            (invoice_id,),
        ).fetchone()
        inv_data = json.loads(inv_row["extracted_data"]) if inv_row and inv_row["extracted_data"] else {}
        formatted = inv_data.get("data", {})
        vendor_name = inv_row["vendor_name"] if inv_row else "Unknown"

        if notification_type == "operational":
            flag_info = payload.get("flag", {})
            instr = get_agent_instructions(conn, "notifier")
            system_prompt = (
                f"{instr['role_description']}\n"
                "Return ONLY valid JSON, no preamble:\n"
                '{"title": string, "body": string, "severity": "info"|"warning"|"critical"}'
            )
            user_prompt = (
                f"Generate an operational notification for a mid-pipeline flag.\n"
                f"Invoice ID: {invoice_id}\nVendor: {vendor_name}\n"
                f"Flag details: {json.dumps(flag_info)}\n"
                f"Grand total: {formatted.get('grand_total', 'unknown')} {formatted.get('currency', 'USD')}"
            )
        else:
            final_row = conn.execute(
                "SELECT verdict, summary, flags, recommendations FROM final_output WHERE invoice_id=?",
                (invoice_id,),
            ).fetchone()
            final = dict(final_row) if final_row else {}

            instr = get_agent_instructions(conn, "notifier")
            system_prompt = (
                f"{instr['role_description']}\n"
                "Return ONLY valid JSON, no preamble:\n"
                '{"title": string, "body": string, "severity": "info"|"warning"|"critical"}'
            )
            user_prompt = (
                f"Generate a summary notification for a completed invoice.\n"
                f"Invoice ID: {invoice_id}\nVendor: {vendor_name}\n"
                f"Verdict: {final.get('verdict', 'unknown')}\n"
                f"Summary: {final.get('summary', '')}\n"
                f"Flags: {final.get('flags', '[]')}\n"
                f"Recommendations: {final.get('recommendations', '[]')}"
            )

        update_queue_status(conn, queue_id, "processing")

        content, pt, ct = call_openai_with_retry(client, "notifier", MODEL, system_prompt, user_prompt)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"notifier LLM returned non-JSON: {e}")

        notification_id = str(uuid.uuid4())
        severity = result.get("severity", "info")

        with conn:
            conn.execute(
                """INSERT INTO notifications
                   (notification_id, invoice_id, notification_type, title, body, severity, acknowledged, created_at)
                   VALUES (?,?,?,?,?,?,0,?)""",
                (notification_id, invoice_id, notification_type,
                 result.get("title", "Invoice Notification"),
                 result.get("body", ""),
                 severity, _now()),
            )
            log_token_usage(conn, "notifier", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "notifier", f"notification_{notification_type}",
                f"Notification created: {result.get('title', '')}",
                {"type": notification_type},
                {"notification_id": notification_id, "severity": severity},
                "success",
            )
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[notifier] Invoice {invoice_id}: {notification_type} notification created.")
        return {"status": "success", "invoice_id": invoice_id, "notification_id": notification_id}

    except Exception as e:
        logger.error(f"[notifier] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(conn, invoice_id, "notifier", "notifier_failed", str(e), {}, {}, "failure")
            update_queue_status(conn, queue_id, "failed")
        raise
