import sqlite3
import logging
from .connection import get_connection

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
-- 1. invoices
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id   TEXT PRIMARY KEY,
    raw_file_path TEXT,
    extracted_data TEXT,
    current_status TEXT NOT NULL DEFAULT 'received'
        CHECK(current_status IN ('received','extracting','formatting','processing',
                                  'flagged','awaiting_human','decision_made',
                                  'completed','failed','rolled_back')),
    vendor_name  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. queue
CREATE TABLE IF NOT EXISTS queue (
    queue_id    TEXT PRIMARY KEY,
    invoice_id  TEXT NOT NULL REFERENCES invoices(invoice_id),
    agent_name  TEXT NOT NULL,
    payload     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','processing','completed','failed')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. event_log  (append-only, enforced by triggers below)
CREATE TABLE IF NOT EXISTS event_log (
    event_id        TEXT PRIMARY KEY,
    invoice_id      TEXT NOT NULL REFERENCES invoices(invoice_id),
    agent_name      TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    reasoning       TEXT,
    input_snapshot  TEXT,
    output_snapshot TEXT,
    status          TEXT NOT NULL
        CHECK(status IN ('success','failure','flagged','skipped')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Prevent UPDATE on event_log
CREATE TRIGGER IF NOT EXISTS prevent_event_log_update
BEFORE UPDATE ON event_log
BEGIN
    SELECT RAISE(ABORT, 'event_log is immutable: updates are not allowed');
END;

-- Prevent DELETE on event_log
CREATE TRIGGER IF NOT EXISTS prevent_event_log_delete
BEFORE DELETE ON event_log
BEGIN
    SELECT RAISE(ABORT, 'event_log is immutable: deletes are not allowed');
END;

-- 4. agent_instructions
CREATE TABLE IF NOT EXISTS agent_instructions (
    instruction_id     TEXT PRIMARY KEY,
    agent_name         TEXT NOT NULL UNIQUE,
    role_description   TEXT NOT NULL,
    memory_access      TEXT,
    decision_methodology TEXT,
    version            INTEGER NOT NULL DEFAULT 1,
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by         TEXT NOT NULL DEFAULT 'system'
);

-- 5. system_knowledge
CREATE TABLE IF NOT EXISTS system_knowledge (
    knowledge_id TEXT PRIMARY KEY,
    category     TEXT NOT NULL
        CHECK(category IN ('approved_services','approved_vendors','cost_centers',
                           'anomaly_rules','decision_weights')),
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by   TEXT NOT NULL DEFAULT 'system'
);

-- 6. operational_memory
CREATE TABLE IF NOT EXISTS operational_memory (
    memory_id    TEXT PRIMARY KEY,
    category     TEXT NOT NULL
        CHECK(category IN ('vendor_history','invoice_patterns','flag_history',
                           'agent_suggestions')),
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    suggested_by TEXT NOT NULL,
    approved_by  TEXT,
    status       TEXT NOT NULL DEFAULT 'pending_approval'
        CHECK(status IN ('pending_approval','approved','rejected')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 7. user_actions
CREATE TABLE IF NOT EXISTS user_actions (
    action_id    TEXT PRIMARY KEY,
    invoice_id   TEXT NOT NULL REFERENCES invoices(invoice_id),
    action_type  TEXT NOT NULL
        CHECK(action_type IN ('approve_flag','reject_flag','approve_memory_write',
                              'reject_memory_write','trigger_rerun',
                              'approve_agent_change','rollback')),
    performed_by TEXT NOT NULL,
    reasoning    TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 8. final_output
CREATE TABLE IF NOT EXISTS final_output (
    output_id        TEXT PRIMARY KEY,
    invoice_id       TEXT NOT NULL REFERENCES invoices(invoice_id),
    verdict          TEXT NOT NULL
        CHECK(verdict IN ('approved','flagged','rejected','requires_human')),
    summary          TEXT,
    flags            TEXT,
    recommendations  TEXT,
    pattern_insights TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 9. notifications
CREATE TABLE IF NOT EXISTS notifications (
    notification_id   TEXT PRIMARY KEY,
    invoice_id        TEXT NOT NULL REFERENCES invoices(invoice_id),
    notification_type TEXT NOT NULL
        CHECK(notification_type IN ('operational','summary')),
    title             TEXT NOT NULL,
    body              TEXT,
    severity          TEXT NOT NULL DEFAULT 'info'
        CHECK(severity IN ('info','warning','critical')),
    acknowledged      INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 10. token_usage
CREATE TABLE IF NOT EXISTS token_usage (
    usage_id          TEXT PRIMARY KEY,
    agent_name        TEXT NOT NULL,
    invoice_id        TEXT NOT NULL REFERENCES invoices(invoice_id),
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL DEFAULT 0.0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_queue_invoice_status ON queue(invoice_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(current_status);
CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_log_invoice ON event_log(invoice_id);
CREATE INDEX IF NOT EXISTS idx_event_log_agent ON event_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_event_log_invoice_agent ON event_log(invoice_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_notifications_pending ON notifications(acknowledged);
CREATE INDEX IF NOT EXISTS idx_notifications_invoice ON notifications(invoice_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_agent ON token_usage(agent_name);
CREATE INDEX IF NOT EXISTS idx_token_usage_invoice ON token_usage(invoice_id);
CREATE INDEX IF NOT EXISTS idx_final_output_invoice ON final_output(invoice_id);
CREATE INDEX IF NOT EXISTS idx_user_actions_invoice ON user_actions(invoice_id);
CREATE INDEX IF NOT EXISTS idx_operational_memory_status ON operational_memory(status);
CREATE INDEX IF NOT EXISTS idx_operational_memory_category_key ON operational_memory(category, key);
CREATE INDEX IF NOT EXISTS idx_system_knowledge_category ON system_knowledge(category);
"""


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Schema created.")
