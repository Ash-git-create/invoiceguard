import uuid
import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from openai import OpenAI

from .base import update_invoice_status, log_event, _now
from ..database.connection import get_connection
from . import extractor, formatter, service_check, anomaly_check, pattern_recognition, decision_agent, notifier

logger = logging.getLogger(__name__)

PARALLEL_AGENTS = ["service_check", "anomaly_check", "pattern_recognition"]
AGENT_MAP = {
    "extractor": extractor,
    "formatter": formatter,
    "service_check": service_check,
    "anomaly_check": anomaly_check,
    "pattern_recognition": pattern_recognition,
    "decision_agent": decision_agent,
    "notifier": notifier,
}


def _post_queue_item(conn, invoice_id: str, agent_name: str, payload: dict = None) -> str:
    queue_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO queue (queue_id, invoice_id, agent_name, payload, status, retry_count, max_retries, created_at, updated_at)
           VALUES (?,?,?,?,?,0,3,?,?)""",
        (queue_id, invoice_id, agent_name, json.dumps(payload or {}), "pending", _now(), _now()),
    )
    return queue_id


def _get_queue_item(conn, queue_id: str) -> dict:
    row = conn.execute("SELECT * FROM queue WHERE queue_id=?", (queue_id,)).fetchone()
    return dict(row) if row else None


def _fire_operational_notification(invoice_id: str, flag: dict, client: OpenAI):
    conn = get_connection()
    queue_id = _post_queue_item(conn, invoice_id, "notifier", {"notification_type": "operational", "flag": flag})
    conn.commit()
    item = _get_queue_item(conn, queue_id)
    try:
        notifier.run(item, client)
    except Exception as e:
        logger.warning(f"[orchestrator] Operational notifier failed: {e}")


def _run_agent_with_retry(agent_name: str, queue_id: str, client: OpenAI) -> dict:
    conn = get_connection()
    item = _get_queue_item(conn, queue_id)
    invoice_id = item["invoice_id"]
    max_retries = item["max_retries"]
    delay = 2

    for attempt in range(max_retries + 1):
        try:
            module = AGENT_MAP[agent_name]
            result = module.run(item, client)
            return result
        except RuntimeError as e:
            err_str = str(e)
            if "COST LIMIT EXCEEDED" in err_str:
                raise
            is_transient = any(kw in err_str.lower() for kw in ["timeout", "rate limit", "connection", "temporary", "database is locked", "locked"])
            if is_transient and attempt < max_retries:
                logger.warning(f"[orchestrator] Transient error in {agent_name} attempt {attempt+1}: {e}. Retry in {delay}s.")
                conn.execute("UPDATE queue SET retry_count=retry_count+1, updated_at=? WHERE queue_id=?", (_now(), queue_id))
                conn.commit()
                time.sleep(delay)
                delay *= 2
                item = _get_queue_item(conn, queue_id)
            else:
                _handle_tier2_error(agent_name, invoice_id, queue_id, e, client)
                raise
        except Exception as e:
            _handle_tier2_error(agent_name, invoice_id, queue_id, e, client)
            raise

    raise RuntimeError(f"[orchestrator] {agent_name} exhausted all retries")


def _handle_tier2_error(agent_name: str, invoice_id: str, queue_id: str, error: Exception, client: OpenAI):
    logger.error(f"[orchestrator] Tier 2 error in {agent_name}: {error}")
    conn = get_connection()
    with conn:
        log_event(conn, invoice_id, "orchestrator", f"{agent_name}_tier2_error",
                  f"Non-retryable error: {error}", {}, {}, "failure")
        update_invoice_status(conn, invoice_id, "failed")

    try:
        conn2 = get_connection()
        notif_id = str(uuid.uuid4())
        conn2.execute(
            """INSERT INTO notifications
               (notification_id, invoice_id, notification_type, title, body, severity, acknowledged, created_at)
               VALUES (?,?,?,?,?,?,0,?)""",
            (notif_id, invoice_id, "operational",
             f"Pipeline Failure: {agent_name}",
             f"Invoice {invoice_id} failed at agent {agent_name}. Error: {error}. Human action required.",
             "critical", _now()),
        )
        conn2.commit()
    except Exception as ne:
        logger.error(f"[orchestrator] Failed to write Tier 2 notification: {ne}")


def _suggest_memory_write(conn, invoice_id: str, vendor_name: str, invoice_data: dict):
    memory_id = str(uuid.uuid4())
    conn.execute(
        """INSERT OR IGNORE INTO operational_memory
           (memory_id, category, key, value, suggested_by, approved_by, status, created_at)
           VALUES (?,?,?,?,?,NULL,'pending_approval',?)""",
        (
            memory_id,
            "vendor_history",
            vendor_name,
            json.dumps({
                "vendor_name": vendor_name,
                "last_invoice_id": invoice_id,
                "grand_total": invoice_data.get("grand_total", 0),
                "line_items": invoice_data.get("line_items", []),
                "invoice_date": invoice_data.get("invoice_date", ""),
                "suggested_update": True,
            }),
            "orchestrator",
            _now(),
        ),
    )


def process_invoice(invoice_id: str, client: OpenAI):
    conn = get_connection()
    logger.info(f"[orchestrator] Starting pipeline for invoice {invoice_id}")

    try:
        with conn:
            update_invoice_status(conn, invoice_id, "received")
            log_event(conn, invoice_id, "orchestrator", "pipeline_start",
                      "Pipeline initiated", {}, {}, "success")

        # Step 1: Extractor
        with conn:
            extract_qid = _post_queue_item(conn, invoice_id, "extractor")
        _run_agent_with_retry("extractor", extract_qid, client)

        # Step 2: Formatter
        with conn:
            format_qid = _post_queue_item(conn, invoice_id, "formatter")
        formatter_result = _run_agent_with_retry("formatter", format_qid, client)

        # Fire operational notifications for formatter flags
        for flag in formatter_result.get("flags", []):
            threading.Thread(target=_fire_operational_notification, args=(invoice_id, flag, client), daemon=True).start()

        # Step 3: Parallel — service_check, anomaly_check, pattern_recognition
        with conn:
            update_invoice_status(conn, invoice_id, "processing")
            parallel_qids = {}
            for agent_name in PARALLEL_AGENTS:
                parallel_qids[agent_name] = _post_queue_item(conn, invoice_id, agent_name)

        parallel_results = {}
        parallel_errors = {}

        def _run_parallel(agent_name):
            return agent_name, _run_agent_with_retry(agent_name, parallel_qids[agent_name], client)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_run_parallel, name): name for name in PARALLEL_AGENTS}
            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    name, result = future.result()
                    parallel_results[name] = result
                    for flag in result.get("flags", []):
                        threading.Thread(
                            target=_fire_operational_notification,
                            args=(invoice_id, flag, client),
                            daemon=True,
                        ).start()
                except Exception as e:
                    parallel_errors[agent_name] = str(e)
                    logger.error(f"[orchestrator] Parallel agent {agent_name} failed: {e}")

        if len(parallel_errors) == len(PARALLEL_AGENTS):
            raise RuntimeError("All parallel agents failed.")

        # Step 4: Decision agent
        with conn:
            decision_qid = _post_queue_item(conn, invoice_id, "decision_agent")
        decision_result = _run_agent_with_retry("decision_agent", decision_qid, client)
        verdict = decision_result.get("verdict", "requires_human")

        # Step 5: Summary notifier
        with conn:
            notif_qid = _post_queue_item(conn, invoice_id, "notifier", {"notification_type": "summary"})
        _run_agent_with_retry("notifier", notif_qid, client)

        # Suggest memory update (pending human approval)
        inv_row = conn.execute("SELECT extracted_data, vendor_name FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        if inv_row and inv_row["extracted_data"]:
            inv_data = json.loads(inv_row["extracted_data"])
            formatted = inv_data.get("data", {})
            vendor_name = inv_row["vendor_name"] or formatted.get("vendor_name", "Unknown")
            with conn:
                _suggest_memory_write(conn, invoice_id, vendor_name, formatted)

        with conn:
            log_event(conn, invoice_id, "orchestrator", "pipeline_complete",
                      f"Pipeline completed. Verdict: {verdict}", {}, {"verdict": verdict}, "success")

        logger.info(f"[orchestrator] Pipeline complete for {invoice_id}. Verdict: {verdict}")
        return {"status": "complete", "invoice_id": invoice_id, "verdict": verdict}

    except Exception as e:
        logger.error(f"[orchestrator] Pipeline failed for {invoice_id}: {e}")
        conn = get_connection()
        with conn:
            log_event(conn, invoice_id, "orchestrator", "pipeline_failed",
                      str(e), {}, {}, "failure")
            update_invoice_status(conn, invoice_id, "failed")
        return {"status": "failed", "invoice_id": invoice_id, "error": str(e)}


def rollback_invoice(invoice_id: str):
    conn = get_connection()
    logger.info(f"[orchestrator] Rolling back invoice {invoice_id}")

    events = conn.execute(
        "SELECT * FROM event_log WHERE invoice_id=? ORDER BY created_at DESC",
        (invoice_id,),
    ).fetchall()

    with conn:
        for event in events:
            log_event(
                conn, invoice_id, "orchestrator",
                f"rollback_{event['event_type']}",
                f"Rolling back: {event['event_type']} by {event['agent_name']}",
                {"original_event_id": event["event_id"]},
                {},
                "success",
            )
        conn.execute(
            "UPDATE invoices SET current_status='rolled_back', updated_at=? WHERE invoice_id=?",
            (_now(), invoice_id),
        )

    logger.info(f"[orchestrator] Rollback complete for invoice {invoice_id}")
    return {"status": "rolled_back", "invoice_id": invoice_id}


def rerun_invoice(invoice_id: str, client: OpenAI, force: bool = False):
    conn = get_connection()
    inv = conn.execute("SELECT * FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
    if not inv:
        raise RuntimeError(f"Invoice {invoice_id} not found")

    prior_events = conn.execute(
        "SELECT COUNT(*) as cnt FROM event_log WHERE invoice_id=?", (invoice_id,)
    ).fetchone()

    if prior_events["cnt"] > 0 and not force:
        return {
            "status": "confirmation_required",
            "message": "Invoice was already processed. Rerun will produce the same result unless agents or invoice file changed. Pass force=true to confirm.",
            "invoice_id": invoice_id,
        }

    with conn:
        conn.execute(
            "UPDATE invoices SET current_status='received', updated_at=? WHERE invoice_id=?",
            (_now(), invoice_id),
        )
        conn.execute("DELETE FROM queue WHERE invoice_id=?", (invoice_id,))
        log_event(conn, invoice_id, "orchestrator", "rerun_initiated",
                  "Invoice rerun triggered by human action", {}, {}, "success")

    return process_invoice(invoice_id, client)
