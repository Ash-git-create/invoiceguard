import json
import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify

from ..database.connection import get_connection

logger = logging.getLogger(__name__)
observability_bp = Blueprint("observability", __name__)

AGENT_NAMES = ["extractor", "formatter", "service_check", "anomaly_check",
               "pattern_recognition", "decision_agent", "notifier"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


@observability_bp.route("/api/observability/pipeline-health", methods=["GET"])
def pipeline_health():
    conn = get_connection()
    result = {}

    for agent in AGENT_NAMES:
        for period_label, days in [("7d", 7), ("30d", 30)]:
            since = _days_ago(days)
            rows = conn.execute(
                """SELECT status, COUNT(*) as cnt,
                          AVG(CAST((julianday('now') - julianday(created_at)) * 86400 AS INTEGER)) as avg_age
                   FROM event_log
                   WHERE agent_name=? AND created_at >= ?
                   GROUP BY status""",
                (agent, since),
            ).fetchall()

            total = sum(r["cnt"] for r in rows)
            success = next((r["cnt"] for r in rows if r["status"] == "success"), 0)
            flagged = next((r["cnt"] for r in rows if r["status"] == "flagged"), 0)
            failure = next((r["cnt"] for r in rows if r["status"] == "failure"), 0)

            if agent not in result:
                result[agent] = {}
            result[agent][period_label] = {
                "total": total,
                "success_rate": round(success / total, 3) if total > 0 else None,
                "failure_rate": round(failure / total, 3) if total > 0 else None,
                "flag_rate": round(flagged / total, 3) if total > 0 else None,
            }

    return jsonify(result)


@observability_bp.route("/api/observability/invoice/<invoice_id>/trace", methods=["GET"])
def invoice_trace(invoice_id):
    conn = get_connection()
    inv = conn.execute("SELECT * FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
    if not inv:
        return jsonify({"error": "Invoice not found"}), 404

    events = conn.execute(
        "SELECT * FROM event_log WHERE invoice_id=? ORDER BY created_at",
        (invoice_id,),
    ).fetchall()

    trace_events = []
    prev_time = None
    for ev in events:
        e = dict(ev)
        try:
            e["input_snapshot"] = json.loads(e["input_snapshot"]) if e.get("input_snapshot") else None
        except Exception:
            pass
        try:
            e["output_snapshot"] = json.loads(e["output_snapshot"]) if e.get("output_snapshot") else None
        except Exception:
            pass
        trace_events.append(e)

    queue_items = conn.execute(
        "SELECT * FROM queue WHERE invoice_id=? ORDER BY created_at",
        (invoice_id,),
    ).fetchall()

    final = conn.execute("SELECT * FROM final_output WHERE invoice_id=?", (invoice_id,)).fetchone()
    final_dict = None
    if final:
        final_dict = dict(final)
        for f in ("flags", "recommendations", "pattern_insights"):
            try:
                final_dict[f] = json.loads(final_dict[f]) if final_dict.get(f) else None
            except Exception:
                pass

    return jsonify({
        "invoice": dict(inv),
        "events": trace_events,
        "queue": [dict(q) for q in queue_items],
        "final_output": final_dict,
    })


@observability_bp.route("/api/observability/anomalies", methods=["GET"])
def system_anomalies():
    conn = get_connection()
    since_7d = _days_ago(7)
    anomalies = []

    # Agent failure rate spike
    for agent in AGENT_NAMES:
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN status='failure' THEN 1 ELSE 0 END) as failures
               FROM event_log WHERE agent_name=? AND created_at >= ?""",
            (agent, since_7d),
        ).fetchone()
        if row["total"] > 0:
            failure_rate = row["failures"] / row["total"]
            if failure_rate > 0.3:
                anomalies.append({
                    "type": "agent_failure_spike",
                    "agent": agent,
                    "failure_rate": round(failure_rate, 3),
                    "severity": "critical" if failure_rate > 0.5 else "warning",
                    "detail": f"{agent} failure rate is {failure_rate:.1%} over 7 days",
                })

    # Flagging rate increasing
    flag_row = conn.execute(
        """SELECT COUNT(*) as total,
                  SUM(CASE WHEN status='flagged' THEN 1 ELSE 0 END) as flagged
           FROM event_log WHERE created_at >= ?""",
        (since_7d,),
    ).fetchone()
    if flag_row["total"] > 0:
        flag_rate = flag_row["flagged"] / flag_row["total"]
        if flag_rate > 0.4:
            anomalies.append({
                "type": "high_flag_rate",
                "flag_rate": round(flag_rate, 3),
                "severity": "warning",
                "detail": f"System-wide flag rate is {flag_rate:.1%} over 7 days",
            })

    # Vendors flagged repeatedly
    vendor_flags = conn.execute(
        """SELECT i.vendor_name, COUNT(*) as flag_count
           FROM event_log e JOIN invoices i ON i.invoice_id = e.invoice_id
           WHERE e.status='flagged' AND e.created_at >= ?
           GROUP BY i.vendor_name
           HAVING flag_count >= 3""",
        (since_7d,),
    ).fetchall()
    for vf in vendor_flags:
        anomalies.append({
            "type": "repeat_vendor_flags",
            "vendor": vf["vendor_name"],
            "flag_count": vf["flag_count"],
            "severity": "warning",
            "detail": f"Vendor '{vf['vendor_name']}' has been flagged {vf['flag_count']} times in 7 days",
        })

    return jsonify(anomalies)


@observability_bp.route("/api/observability/metrics", methods=["GET"])
def metrics():
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) as cnt FROM invoices").fetchone()["cnt"]
    approved = conn.execute("SELECT COUNT(*) as cnt FROM final_output WHERE verdict='approved'").fetchone()["cnt"]
    flagged = conn.execute("SELECT COUNT(*) as cnt FROM final_output WHERE verdict IN ('flagged','requires_human')").fetchone()["cnt"]
    rejected = conn.execute("SELECT COUNT(*) as cnt FROM final_output WHERE verdict='rejected'").fetchone()["cnt"]
    rolled_back = conn.execute("SELECT COUNT(*) as cnt FROM invoices WHERE current_status='rolled_back'").fetchone()["cnt"]

    vendor_rows = conn.execute(
        """SELECT i.vendor_name,
                  COUNT(*) as invoice_count,
                  SUM(CASE WHEN e.status='flagged' THEN 1 ELSE 0 END) as flag_count
           FROM invoices i
           LEFT JOIN event_log e ON e.invoice_id = i.invoice_id
           WHERE i.vendor_name IS NOT NULL
           GROUP BY i.vendor_name""",
    ).fetchall()

    vendor_scores = []
    for r in vendor_rows:
        if r["invoice_count"] > 0:
            reliability = 1.0 - (r["flag_count"] / max(r["invoice_count"], 1))
            vendor_scores.append({
                "vendor": r["vendor_name"],
                "invoice_count": r["invoice_count"],
                "flag_count": r["flag_count"],
                "reliability_score": round(max(reliability, 0.0), 3),
            })

    processed_total = approved + flagged + rejected
    return jsonify({
        "total_invoices": total,
        "processed": processed_total,
        "approval_rate": round(approved / processed_total, 3) if processed_total > 0 else None,
        "flag_rate": round(flagged / processed_total, 3) if processed_total > 0 else None,
        "rejection_rate": round(rejected / processed_total, 3) if processed_total > 0 else None,
        "rollback_rate": round(rolled_back / max(total, 1), 3),
        "vendor_reliability_scores": vendor_scores,
    })


@observability_bp.route("/api/observability/token-usage", methods=["GET"])
def token_usage():
    conn = get_connection()

    per_agent = conn.execute(
        """SELECT agent_name, model,
                  SUM(prompt_tokens) as total_prompt_tokens,
                  SUM(completion_tokens) as total_completion_tokens,
                  SUM(cost_usd) as total_cost_usd,
                  COUNT(*) as call_count
           FROM token_usage
           GROUP BY agent_name, model
           ORDER BY total_cost_usd DESC""",
    ).fetchall()

    per_invoice = conn.execute(
        """SELECT invoice_id, SUM(cost_usd) as invoice_cost
           FROM token_usage GROUP BY invoice_id ORDER BY invoice_cost DESC LIMIT 20""",
    ).fetchall()

    cumulative = conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM token_usage").fetchone()["total"]

    daily_trend = conn.execute(
        """SELECT DATE(created_at) as date, SUM(cost_usd) as daily_cost
           FROM token_usage
           GROUP BY DATE(created_at)
           ORDER BY date DESC LIMIT 30""",
    ).fetchall()

    hard_limit = 1.50
    return jsonify({
        "per_agent": [dict(r) for r in per_agent],
        "per_invoice_top20": [dict(r) for r in per_invoice],
        "cumulative_cost_usd": round(cumulative, 6),
        "hard_limit_usd": hard_limit,
        "limit_utilization_pct": round(cumulative / hard_limit * 100, 2),
        "daily_cost_trend": [dict(r) for r in daily_trend],
    })
