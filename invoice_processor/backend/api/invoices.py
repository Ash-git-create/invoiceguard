import uuid
import os
import json
import threading
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from ..database.connection import get_connection
from ..agents import orchestrator
from ..extensions import limiter

logger = logging.getLogger(__name__)

invoices_bp = Blueprint("invoices", __name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".docx", ".xml", ".json", ".eml", ".txt"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


@invoices_bp.route("/api/invoices/upload", methods=["POST"])
@limiter.limit("10 per minute")
def upload_invoice():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    invoice_id = str(uuid.uuid4())
    filename = secure_filename(f"{invoice_id}{ext}")
    file_path = os.path.join(UPLOAD_DIR, filename)
    f.save(file_path)

    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO invoices (invoice_id, raw_file_path, current_status, created_at, updated_at)
               VALUES (?,?,?,?,?)""",
            (invoice_id, file_path, "received", _now(), _now()),
        )

    client = _get_client()
    threading.Thread(
        target=orchestrator.process_invoice,
        args=(invoice_id, client),
        daemon=True,
    ).start()

    return jsonify({"invoice_id": invoice_id, "status": "received", "message": "Pipeline started"}), 202


@invoices_bp.route("/api/invoices", methods=["GET"])
def list_invoices():
    conn = get_connection()
    rows = conn.execute(
        "SELECT invoice_id, vendor_name, current_status, created_at, updated_at FROM invoices ORDER BY created_at DESC LIMIT 100"
    ).fetchall()

    result = []
    for row in rows:
        inv = dict(row)
        flag_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM event_log WHERE invoice_id=? AND status='flagged'",
            (inv["invoice_id"],),
        ).fetchone()["cnt"]
        inv["flag_count"] = flag_count
        result.append(inv)

    return jsonify(result)


@invoices_bp.route("/api/invoices/<invoice_id>", methods=["GET"])
def get_invoice(invoice_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
    if not row:
        return jsonify({"error": "Invoice not found"}), 404

    inv = dict(row)
    if inv.get("extracted_data"):
        try:
            inv["extracted_data"] = json.loads(inv["extracted_data"])
        except Exception:
            pass

    events = conn.execute(
        "SELECT * FROM event_log WHERE invoice_id=? ORDER BY created_at",
        (invoice_id,),
    ).fetchall()
    inv["events"] = [dict(e) for e in events]

    final = conn.execute(
        "SELECT * FROM final_output WHERE invoice_id=?", (invoice_id,)
    ).fetchone()
    if final:
        fo = dict(final)
        for field in ("flags", "recommendations", "pattern_insights"):
            if fo.get(field):
                try:
                    fo[field] = json.loads(fo[field])
                except Exception:
                    pass
        inv["final_output"] = fo
    else:
        inv["final_output"] = None

    return jsonify(inv)


@invoices_bp.route("/api/invoices/<invoice_id>/approve-flag", methods=["POST"])
def approve_flag(invoice_id):
    conn = get_connection()
    data = request.get_json() or {}
    performed_by = data.get("performed_by", "human")
    reasoning = data.get("reasoning", "")

    with conn:
        action_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO user_actions (action_id, invoice_id, action_type, performed_by, reasoning, created_at)
               VALUES (?,?,?,?,?,?)""",
            (action_id, invoice_id, "approve_flag", performed_by, reasoning, _now()),
        )
        conn.execute(
            "UPDATE invoices SET current_status='completed', updated_at=? WHERE invoice_id=?",
            (_now(), invoice_id),
        )

        # Feedback loop (item 17): record human override so decision_agent can learn over time
        inv_row = conn.execute(
            "SELECT vendor_name FROM invoices WHERE invoice_id=?", (invoice_id,)
        ).fetchone()
        final_row = conn.execute(
            "SELECT verdict, flags FROM final_output WHERE invoice_id=?", (invoice_id,)
        ).fetchone()

        if inv_row and final_row:
            vendor = inv_row["vendor_name"] or "unknown"
            try:
                flags_list = json.loads(final_row["flags"]) if final_row["flags"] else []
            except Exception:
                flags_list = []

            memory_value = json.dumps({
                "vendor": vendor,
                "original_verdict": final_row["verdict"],
                "human_action": "approved_override",
                "reasoning": reasoning,
                "flags_overridden": flags_list,
                "timestamp": _now(),
            })
            conn.execute(
                """INSERT INTO operational_memory
                   (memory_id, category, key, value, suggested_by, approved_by, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), "flag_history",
                    f"{vendor}_approved_override",
                    memory_value, "human_feedback", performed_by, "approved", _now(),
                ),
            )
            logger.info(f"[feedback] Recorded human approval override for vendor '{vendor}' on invoice {invoice_id}")

    return jsonify({"status": "flag_approved", "action_id": action_id})


@invoices_bp.route("/api/invoices/<invoice_id>/reject-flag", methods=["POST"])
def reject_flag(invoice_id):
    conn = get_connection()
    data = request.get_json() or {}
    performed_by = data.get("performed_by", "human")
    reasoning = data.get("reasoning", "")

    with conn:
        action_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO user_actions (action_id, invoice_id, action_type, performed_by, reasoning, created_at)
               VALUES (?,?,?,?,?,?)""",
            (action_id, invoice_id, "reject_flag", performed_by, reasoning, _now()),
        )
        conn.execute(
            "UPDATE invoices SET current_status='flagged', updated_at=? WHERE invoice_id=?",
            (_now(), invoice_id),
        )

        # Feedback loop: record confirmed rejection so decision_agent sees flag is valid for this vendor
        inv_row = conn.execute(
            "SELECT vendor_name FROM invoices WHERE invoice_id=?", (invoice_id,)
        ).fetchone()
        final_row = conn.execute(
            "SELECT verdict, flags FROM final_output WHERE invoice_id=?", (invoice_id,)
        ).fetchone()

        if inv_row and final_row:
            vendor = inv_row["vendor_name"] or "unknown"
            try:
                flags_list = json.loads(final_row["flags"]) if final_row["flags"] else []
            except Exception:
                flags_list = []

            memory_value = json.dumps({
                "vendor": vendor,
                "original_verdict": final_row["verdict"],
                "human_action": "confirmed_rejection",
                "reasoning": reasoning,
                "flags_confirmed": flags_list,
                "timestamp": _now(),
            })
            conn.execute(
                """INSERT INTO operational_memory
                   (memory_id, category, key, value, suggested_by, approved_by, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), "flag_history",
                    f"{vendor}_confirmed_rejection",
                    memory_value, "human_feedback", performed_by, "approved", _now(),
                ),
            )

    return jsonify({"status": "flag_rejected", "action_id": action_id})


@invoices_bp.route("/api/invoices/<invoice_id>/rollback", methods=["POST"])
def rollback(invoice_id):
    conn = get_connection()
    data = request.get_json() or {}
    performed_by = data.get("performed_by", "human")
    reasoning = data.get("reasoning", "")

    with conn:
        conn.execute(
            """INSERT INTO user_actions (action_id, invoice_id, action_type, performed_by, reasoning, created_at)
               VALUES (?,?,?,?,?,?)""",
            (str(uuid.uuid4()), invoice_id, "rollback", performed_by, reasoning, _now()),
        )

    result = orchestrator.rollback_invoice(invoice_id)
    return jsonify(result)


@invoices_bp.route("/api/invoices/<invoice_id>/rerun", methods=["POST"])
def rerun(invoice_id):
    data = request.get_json() or {}
    force = data.get("force", False)
    performed_by = data.get("performed_by", "human")

    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO user_actions (action_id, invoice_id, action_type, performed_by, reasoning, created_at)
               VALUES (?,?,?,?,?,?)""",
            (str(uuid.uuid4()), invoice_id, "trigger_rerun", performed_by, "Rerun requested", _now()),
        )

    client = _get_client()
    result = orchestrator.rerun_invoice(invoice_id, client, force=force)

    if result.get("status") == "confirmation_required":
        return jsonify(result), 409

    return jsonify({"status": "rerun_started", "invoice_id": invoice_id})
