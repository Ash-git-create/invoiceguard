"""
Background observability monitor. Runs as a separate thread alongside the API server.
Polls the database periodically and writes system-level anomaly notifications.
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta

from ..database.connection import get_connection

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


def _now():
    return datetime.now(timezone.utc).isoformat()


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _check_cost_limit(conn):
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM token_usage").fetchone()
    total = row["total"] if row else 0.0
    if total >= 1.50:
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE title LIKE 'COST LIMIT%' AND acknowledged=0"
        ).fetchone()["cnt"]
        if existing == 0:
            conn.execute(
                """INSERT INTO notifications
                   (notification_id, invoice_id, notification_type, title, body, severity, acknowledged, created_at)
                   VALUES (?,?,?,?,?,?,0,?)""",
                (
                    str(uuid.uuid4()),
                    "00000000-0000-0000-0000-000000000000",
                    "operational",
                    "COST LIMIT REACHED - Pipeline Paused",
                    f"Cumulative API spend ${total:.4f} has reached the $1.50 hard limit. Acknowledge to resume.",
                    "critical",
                    _now(),
                ),
            )
            conn.commit()
            logger.warning(f"[monitor] Cost limit notification written: ${total:.4f}")


def _check_agent_health(conn):
    since = _days_ago(1)
    agents = ["extractor", "formatter", "service_check", "anomaly_check",
              "pattern_recognition", "decision_agent", "notifier"]
    for agent in agents:
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN status='failure' THEN 1 ELSE 0 END) as failures
               FROM event_log WHERE agent_name=? AND created_at >= ?""",
            (agent, since),
        ).fetchone()
        if row["total"] >= 5:
            failure_rate = row["failures"] / row["total"]
            if failure_rate > 0.5:
                key_title = f"Agent Health Alert: {agent} failure rate {failure_rate:.0%}"
                existing = conn.execute(
                    "SELECT COUNT(*) as cnt FROM notifications WHERE title=? AND acknowledged=0",
                    (key_title,),
                ).fetchone()["cnt"]
                if existing == 0:
                    conn.execute(
                        """INSERT INTO notifications
                           (notification_id, invoice_id, notification_type, title, body, severity, acknowledged, created_at)
                           VALUES (?,?,?,?,?,?,0,?)""",
                        (
                            str(uuid.uuid4()),
                            "00000000-0000-0000-0000-000000000000",
                            "operational",
                            key_title,
                            f"{agent} has a {failure_rate:.0%} failure rate over the last 24 hours ({row['failures']}/{row['total']} events).",
                            "critical",
                            _now(),
                        ),
                    )
                    conn.commit()
                    logger.warning(f"[monitor] Health alert written for {agent}")


def _check_stalled_invoices(conn):
    """Flag invoices stuck in processing state for > 10 minutes."""
    threshold = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    stalled = conn.execute(
        """SELECT invoice_id, current_status, vendor_name, updated_at
           FROM invoices
           WHERE current_status IN ('extracting','formatting','processing','decision_made')
           AND updated_at < ?""",
        (threshold,),
    ).fetchall()
    for inv in stalled:
        title = f"Stalled Invoice: {inv['invoice_id'][:8]}..."
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE title=? AND acknowledged=0",
            (title,),
        ).fetchone()["cnt"]
        if existing == 0:
            conn.execute(
                """INSERT INTO notifications
                   (notification_id, invoice_id, notification_type, title, body, severity, acknowledged, created_at)
                   VALUES (?,?,?,?,?,?,0,?)""",
                (
                    str(uuid.uuid4()),
                    inv["invoice_id"],
                    "operational",
                    title,
                    f"Invoice {inv['invoice_id']} (vendor: {inv['vendor_name']}) has been stuck in '{inv['current_status']}' since {inv['updated_at']}.",
                    "warning",
                    _now(),
                ),
            )
            conn.commit()


def run_checks():
    conn = get_connection()
    try:
        _check_cost_limit(conn)
        _check_agent_health(conn)
        _check_stalled_invoices(conn)
    except Exception as e:
        logger.error(f"[monitor] Error during health checks: {e}")


def start_monitor(interval: int = POLL_INTERVAL_SECONDS):
    def _loop():
        logger.info(f"[monitor] Starting observability monitor (interval={interval}s)")
        while True:
            run_checks()
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name="observability-monitor")
    t.start()
    logger.info("[monitor] Observability monitor thread started.")
    return t
