import uuid
import json
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

from ..database.connection import get_connection

logger = logging.getLogger(__name__)
memory_bp = Blueprint("memory", __name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


@memory_bp.route("/api/memory/pending", methods=["GET"])
def get_pending_memory():
    conn = get_connection()
    rows = conn.execute(
        """SELECT m.*, i.vendor_name
           FROM operational_memory m
           LEFT JOIN invoices i ON i.vendor_name = m.key
           WHERE m.status = 'pending_approval'
           ORDER BY m.created_at DESC""",
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@memory_bp.route("/api/memory/approve/<memory_id>", methods=["POST"])
def approve_memory(memory_id):
    data = request.get_json() or {}
    approved_by = data.get("approved_by", "human")
    conn = get_connection()

    row = conn.execute("SELECT * FROM operational_memory WHERE memory_id=?", (memory_id,)).fetchone()
    if not row:
        return jsonify({"error": "Memory entry not found"}), 404
    if row["status"] != "pending_approval":
        return jsonify({"error": f"Memory entry is already {row['status']}"}), 400

    with conn:
        conn.execute(
            "UPDATE operational_memory SET status='approved', approved_by=? WHERE memory_id=?",
            (approved_by, memory_id),
        )

    return jsonify({"status": "approved", "memory_id": memory_id})


@memory_bp.route("/api/memory/reject/<memory_id>", methods=["POST"])
def reject_memory(memory_id):
    data = request.get_json() or {}
    rejected_by = data.get("rejected_by", "human")
    conn = get_connection()

    row = conn.execute("SELECT * FROM operational_memory WHERE memory_id=?", (memory_id,)).fetchone()
    if not row:
        return jsonify({"error": "Memory entry not found"}), 404

    with conn:
        conn.execute(
            "UPDATE operational_memory SET status='rejected', approved_by=? WHERE memory_id=?",
            (rejected_by, memory_id),
        )

    return jsonify({"status": "rejected", "memory_id": memory_id})


@memory_bp.route("/api/memory/approved", methods=["GET"])
def get_approved_memory():
    conn = get_connection()
    category = request.args.get("category")
    query = "SELECT * FROM operational_memory WHERE status='approved'"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY created_at DESC LIMIT 100"
    rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["value"] = json.loads(item["value"])
        except Exception:
            pass
        result.append(item)
    return jsonify(result)


@memory_bp.route("/api/memory/system-knowledge", methods=["GET"])
def get_system_knowledge():
    conn = get_connection()
    category = request.args.get("category")
    query = "SELECT * FROM system_knowledge"
    params = []
    if category:
        query += " WHERE category=?"
        params.append(category)
    query += " ORDER BY category, key"
    rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["value"] = json.loads(item["value"])
        except Exception:
            pass
        result.append(item)
    return jsonify(result)


@memory_bp.route("/api/agent-instructions", methods=["GET"])
def get_agent_instructions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM agent_instructions ORDER BY agent_name").fetchall()
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["memory_access"] = json.loads(item["memory_access"]) if item.get("memory_access") else []
        except Exception:
            pass
        result.append(item)
    return jsonify(result)


@memory_bp.route("/api/agent-instructions/approve-change", methods=["POST"])
def approve_agent_instruction_change():
    data = request.get_json() or {}
    agent_name = data.get("agent_name")
    new_methodology = data.get("decision_methodology")
    approved_by = data.get("approved_by", "human")

    if not agent_name or not new_methodology:
        return jsonify({"error": "agent_name and decision_methodology required"}), 400

    conn = get_connection()
    row = conn.execute("SELECT * FROM agent_instructions WHERE agent_name=?", (agent_name,)).fetchone()
    if not row:
        return jsonify({"error": f"Agent {agent_name} not found"}), 404

    action_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            """UPDATE agent_instructions
               SET decision_methodology=?, version=version+1, updated_at=?, updated_by=?
               WHERE agent_name=?""",
            (new_methodology, _now(), approved_by, agent_name),
        )
        conn.execute(
            """INSERT INTO user_actions (action_id, invoice_id, action_type, performed_by, reasoning, created_at)
               VALUES (?,?,?,?,?,?)""",
            (action_id, "00000000-0000-0000-0000-000000000000",
             "approve_agent_change", approved_by,
             f"Updated {agent_name} decision_methodology", _now()),
        )

    return jsonify({"status": "updated", "agent_name": agent_name, "action_id": action_id})
