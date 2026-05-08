import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from ..database.connection import get_connection

logger = logging.getLogger(__name__)
notifications_bp = Blueprint("notifications", __name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


@notifications_bp.route("/api/notifications/pending", methods=["GET"])
def get_pending():
    conn = get_connection()
    rows = conn.execute(
        """SELECT n.*, i.vendor_name
           FROM notifications n
           LEFT JOIN invoices i ON i.invoice_id = n.invoice_id
           WHERE n.acknowledged = 0
           ORDER BY n.created_at DESC""",
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@notifications_bp.route("/api/notifications", methods=["GET"])
def get_all():
    conn = get_connection()
    limit = int(request.args.get("limit", 50))
    invoice_id = request.args.get("invoice_id")

    query = "SELECT n.*, i.vendor_name FROM notifications n LEFT JOIN invoices i ON i.invoice_id = n.invoice_id"
    params = []
    if invoice_id:
        query += " WHERE n.invoice_id=?"
        params.append(invoice_id)
    query += " ORDER BY n.created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@notifications_bp.route("/api/notifications/<notification_id>/acknowledge", methods=["POST"])
def acknowledge(notification_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM notifications WHERE notification_id=?", (notification_id,)).fetchone()
    if not row:
        return jsonify({"error": "Notification not found"}), 404

    with conn:
        conn.execute(
            "UPDATE notifications SET acknowledged=1 WHERE notification_id=?",
            (notification_id,),
        )

    return jsonify({"status": "acknowledged", "notification_id": notification_id})


@notifications_bp.route("/api/notifications/acknowledge-all", methods=["POST"])
def acknowledge_all():
    conn = get_connection()
    with conn:
        conn.execute("UPDATE notifications SET acknowledged=1 WHERE acknowledged=0")
    return jsonify({"status": "all_acknowledged"})
