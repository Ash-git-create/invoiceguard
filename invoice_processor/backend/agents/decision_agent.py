import json
import uuid
import logging
from openai import OpenAI
from pydantic import ValidationError

from .base import (
    log_event, log_token_usage, update_queue_status, update_invoice_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from .schemas import DecisionAgentResponse
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    conn = get_connection()

    try:
        check_cost_limit(conn, "decision_agent", invoice_id)

        agent_events = conn.execute(
            """SELECT agent_name, event_type, reasoning, output_snapshot, status
               FROM event_log
               WHERE invoice_id=? AND agent_name IN ('service_check','anomaly_check','pattern_recognition')
               ORDER BY created_at""",
            (invoice_id,),
        ).fetchall()

        if not agent_events:
            raise RuntimeError(f"No upstream agent events found for invoice {invoice_id}")

        events_summary = []
        all_flags = []
        for ev in agent_events:
            output = json.loads(ev["output_snapshot"]) if ev["output_snapshot"] else {}
            events_summary.append({
                "agent": ev["agent_name"],
                "status": ev["status"],
                "reasoning": ev["reasoning"],
                "flags": output.get("flags", []),
            })
            all_flags.extend(output.get("flags", []))

        weights_rows = conn.execute(
            "SELECT key, value FROM system_knowledge WHERE category='decision_weights'"
        ).fetchall()
        decision_weights = {r["key"]: json.loads(r["value"]) for r in weights_rows}

        inv_row = conn.execute("SELECT extracted_data, vendor_name FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        inv_data = json.loads(inv_row["extracted_data"]) if inv_row and inv_row["extracted_data"] else {}
        formatted = inv_data.get("data", {})
        vendor_name = formatted.get("vendor_name", inv_row["vendor_name"] or "Unknown") if inv_row else "Unknown"

        # Load human override history for this vendor (feedback loop, item 17)
        flag_history_rows = conn.execute(
            """SELECT value FROM operational_memory
               WHERE category='flag_history' AND key LIKE ? AND status='approved'
               ORDER BY created_at DESC LIMIT 5""",
            (f"{vendor_name}%",),
        ).fetchall()
        flag_history = [json.loads(r["value"]) for r in flag_history_rows]

        instr = get_agent_instructions(conn, "decision_agent")
        system_prompt = (
            f"{instr['role_description']}\n"
            f"Methodology: {instr['decision_methodology']}\n\n"
            "Return ONLY valid JSON, no preamble:\n"
            '{"verdict": "approved"|"flagged"|"rejected"|"requires_human", '
            '"summary": string, "reasoning": string, '
            '"flags": [{"agent": string, "reason": string, "severity": string}], '
            '"recommendations": [string], "pattern_insights": string, "confidence": number}'
        )

        history_context = (
            f"\n\nHuman override history for vendor '{vendor_name}' (last {len(flag_history)} records):\n"
            + json.dumps(flag_history, indent=2)
            if flag_history else ""
        )

        user_prompt = (
            f"Invoice: vendor={vendor_name}, "
            f"grand_total={formatted.get('grand_total','?')} {formatted.get('currency','USD')}\n\n"
            f"Agent outputs:\n{json.dumps(events_summary, indent=2)}\n\n"
            f"Decision weights:\n{json.dumps(decision_weights, indent=2)}"
            f"{history_context}\n\n"
            "Apply weighted reasoning. If the vendor has a strong history of human overrides on similar "
            "flags, consider reducing the weight of those flag types. Produce final verdict."
        )

        with conn:
            update_invoice_status(conn, invoice_id, "decision_made")
            update_queue_status(conn, queue_id, "processing")

        content, pt, ct = call_openai_with_retry(client, "decision_agent", MODEL, system_prompt, user_prompt)

        try:
            validated = DecisionAgentResponse.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuntimeError(f"decision_agent response validation failed: {e}")
        result = validated.model_dump()

        verdict = result["verdict"]
        final_status = "completed" if verdict in ("approved", "rejected") else "awaiting_human" if verdict == "requires_human" else "flagged"

        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO final_output
                   (output_id, invoice_id, verdict, summary, flags, recommendations, pattern_insights, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    invoice_id,
                    verdict,
                    result.get("summary", ""),
                    json.dumps(result["flags"] or all_flags),
                    json.dumps(result["recommendations"]),
                    result["pattern_insights"],
                    _now(),
                ),
            )
            log_token_usage(conn, "decision_agent", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "decision_agent", "decision_complete",
                result["reasoning"],
                {"flags_count": len(all_flags)},
                result,
                "success",
            )
            update_invoice_status(conn, invoice_id, final_status)
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[decision_agent] Invoice {invoice_id}: verdict={verdict}")
        return {"status": "success", "invoice_id": invoice_id, "verdict": verdict}

    except Exception as e:
        logger.error(f"[decision_agent] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(conn, invoice_id, "decision_agent", "decision_failed", str(e), {}, {}, "failure")
            update_queue_status(conn, queue_id, "failed")
            update_invoice_status(conn, invoice_id, "failed")
        raise
