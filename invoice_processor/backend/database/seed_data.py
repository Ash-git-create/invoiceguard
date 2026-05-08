import uuid
import json
import logging
from datetime import datetime, timezone
from .connection import get_connection

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


APPROVED_SERVICES = [
    {"key": "SaaS-CRM", "value": {"name": "CRM Software License", "category": "software_license", "max_unit_price": 150.0}},
    {"key": "SaaS-ProjectMgmt", "value": {"name": "Project Management Tool", "category": "software_license", "max_unit_price": 50.0}},
    {"key": "SaaS-Analytics", "value": {"name": "Analytics Platform License", "category": "software_license", "max_unit_price": 300.0}},
    {"key": "SaaS-HRSystem", "value": {"name": "HR Management System", "category": "software_license", "max_unit_price": 200.0}},
    {"key": "SaaS-Accounting", "value": {"name": "Accounting Software License", "category": "software_license", "max_unit_price": 180.0}},
    {"key": "Cloud-AWS", "value": {"name": "AWS Cloud Services", "category": "cloud_service", "max_unit_price": 10000.0}},
    {"key": "Cloud-Azure", "value": {"name": "Microsoft Azure Services", "category": "cloud_service", "max_unit_price": 10000.0}},
    {"key": "Cloud-GCP", "value": {"name": "Google Cloud Platform", "category": "cloud_service", "max_unit_price": 10000.0}},
    {"key": "Cloud-Storage", "value": {"name": "Cloud Storage Service", "category": "cloud_service", "max_unit_price": 500.0}},
    {"key": "Office-Supplies", "value": {"name": "Office Supplies", "category": "office_supplies", "max_unit_price": 500.0}},
    {"key": "Office-Furniture", "value": {"name": "Office Furniture", "category": "office_supplies", "max_unit_price": 2000.0}},
    {"key": "Office-Stationery", "value": {"name": "Stationery and Paper", "category": "office_supplies", "max_unit_price": 200.0}},
    {"key": "Consulting-IT", "value": {"name": "IT Consulting Services", "category": "consulting", "max_unit_price": 250.0}},
    {"key": "Consulting-Legal", "value": {"name": "Legal Consulting Services", "category": "consulting", "max_unit_price": 400.0}},
    {"key": "Consulting-Finance", "value": {"name": "Financial Advisory Services", "category": "consulting", "max_unit_price": 350.0}},
    {"key": "Hardware-Laptop", "value": {"name": "Laptop Computer", "category": "hardware", "max_unit_price": 2500.0}},
    {"key": "Hardware-Monitor", "value": {"name": "Computer Monitor", "category": "hardware", "max_unit_price": 800.0}},
    {"key": "Hardware-Server", "value": {"name": "Server Hardware", "category": "hardware", "max_unit_price": 15000.0}},
    {"key": "Hardware-Network", "value": {"name": "Network Equipment", "category": "hardware", "max_unit_price": 5000.0}},
    {"key": "Maintenance-IT", "value": {"name": "IT Equipment Maintenance", "category": "maintenance", "max_unit_price": 1000.0}},
]

APPROVED_VENDORS = [
    {"key": "VEND-001", "value": {"name": "TechSolutions Inc.", "category": "software", "monthly_spend_limit": 5000.0, "annual_spend_limit": 50000.0, "reliability_score": 0.95, "approved_since": "2022-01-01"}},
    {"key": "VEND-002", "value": {"name": "CloudPlatform Corp.", "category": "cloud", "monthly_spend_limit": 20000.0, "annual_spend_limit": 200000.0, "reliability_score": 0.98, "approved_since": "2021-06-15"}},
    {"key": "VEND-003", "value": {"name": "OfficeWorld Supplies", "category": "office", "monthly_spend_limit": 2000.0, "annual_spend_limit": 20000.0, "reliability_score": 0.90, "approved_since": "2023-03-01"}},
    {"key": "VEND-004", "value": {"name": "Apex Consulting Group", "category": "consulting", "monthly_spend_limit": 15000.0, "annual_spend_limit": 150000.0, "reliability_score": 0.88, "approved_since": "2022-09-01"}},
    {"key": "VEND-005", "value": {"name": "HardwareDirect Ltd.", "category": "hardware", "monthly_spend_limit": 10000.0, "annual_spend_limit": 100000.0, "reliability_score": 0.92, "approved_since": "2021-12-01"}},
    {"key": "VEND-006", "value": {"name": "SoftwarePro Systems", "category": "software", "monthly_spend_limit": 3000.0, "annual_spend_limit": 30000.0, "reliability_score": 0.93, "approved_since": "2023-01-15"}},
    {"key": "VEND-007", "value": {"name": "NetworkFirst Solutions", "category": "hardware", "monthly_spend_limit": 8000.0, "annual_spend_limit": 80000.0, "reliability_score": 0.87, "approved_since": "2022-05-01"}},
    {"key": "VEND-008", "value": {"name": "LegalEagle Partners", "category": "consulting", "monthly_spend_limit": 12000.0, "annual_spend_limit": 120000.0, "reliability_score": 0.91, "approved_since": "2022-07-01"}},
    {"key": "VEND-009", "value": {"name": "FinanceFirst Advisory", "category": "consulting", "monthly_spend_limit": 10000.0, "annual_spend_limit": 100000.0, "reliability_score": 0.94, "approved_since": "2021-11-01"}},
    {"key": "VEND-010", "value": {"name": "DataCenter Pro", "category": "cloud", "monthly_spend_limit": 15000.0, "annual_spend_limit": 150000.0, "reliability_score": 0.96, "approved_since": "2020-08-01"}},
]

ANOMALY_RULES = [
    {"key": "duplicate_threshold", "value": {"description": "Flag if same line item appears more than once with identical description and price", "threshold": 1, "severity": "warning"}},
    {"key": "round_number_bias", "value": {"description": "Flag invoice totals that are suspiciously round (divisible by 1000)", "threshold": 1000, "severity": "info"}},
    {"key": "high_amount_threshold", "value": {"description": "Flag individual line items exceeding this USD amount", "threshold": 5000.0, "severity": "warning"}},
    {"key": "historical_variance", "value": {"description": "Flag invoices where grand_total deviates more than this percentage from vendor historical average", "threshold": 0.30, "severity": "warning"}},
    {"key": "future_invoice_date", "value": {"description": "Flag invoices with invoice_date more than 7 days in the future", "threshold_days": 7, "severity": "critical"}},
]

DECISION_WEIGHTS = [
    {"key": "critical_service_flag", "value": {"weight": 0.95, "description": "Unknown or unauthorized service detected", "auto_reject_threshold": 1}},
    {"key": "anomaly_flag_critical", "value": {"weight": 0.80, "description": "Critical anomaly detected (e.g., future date, major math error)", "auto_flag_threshold": 1}},
    {"key": "anomaly_flag_warning", "value": {"weight": 0.50, "description": "Warning-level anomaly (e.g., round number, moderate variance)", "auto_flag_threshold": 2}},
    {"key": "pattern_deviation", "value": {"weight": 0.40, "description": "Significant deviation from vendor's historical pattern", "auto_flag_threshold": 1}},
    {"key": "math_inconsistency", "value": {"weight": 0.85, "description": "Line items do not sum correctly to totals", "auto_reject_threshold": 1}},
    {"key": "clean_service_check", "value": {"weight": 0.10, "description": "All services verified as approved", "positive": True}},
    {"key": "clean_anomaly_check", "value": {"weight": 0.10, "description": "No anomalies detected", "positive": True}},
    {"key": "known_vendor_bonus", "value": {"weight": 0.05, "description": "Invoice from known approved vendor with high reliability", "positive": True}},
]

AGENT_INSTRUCTIONS = [
    {
        "agent_name": "orchestrator",
        "role_description": "Routes invoices through the processing pipeline. Posts tasks to queue, monitors completion, handles parallel execution of service_check/anomaly_check/pattern_recognition. Applies tiered error handling. Never makes LLM calls.",
        "memory_access": json.dumps(["queue", "event_log", "invoices", "agent_instructions", "operational_memory"]),
        "decision_methodology": "1. On invoice arrival: post extractor task. 2. After extractor: post formatter task. 3. After formatter: post service_check, anomaly_check, pattern_recognition simultaneously. 4. After all three complete: post decision_agent task. 5. On any flag: trigger notifier immediately. 6. On failure: apply tiered error handling.",
    },
    {
        "agent_name": "extractor",
        "role_description": "Extracts raw text and metadata from invoice files. Detects file type and uses appropriate parser. Returns raw text only, does not interpret content.",
        "memory_access": json.dumps(["invoices"]),
        "decision_methodology": "Detect file extension. Use pdfplumber for PDF, pytesseract for images, python-docx for DOCX, native parsers for XML/JSON, email library for .eml. Return all extracted text verbatim. Flag unreadable files as Tier 2 errors.",
    },
    {
        "agent_name": "formatter",
        "role_description": "Structures raw extracted text into standardized invoice JSON. Validates mathematical consistency of line items.",
        "memory_access": json.dumps(["invoices", "system_knowledge:anomaly_rules"]),
        "decision_methodology": "Parse extracted text into: vendor_name, vendor_id, invoice_date, due_date, line_items[], subtotal, tax, grand_total, currency, payment_terms. Verify sum(line_items.total) == subtotal and subtotal + tax == grand_total within 0.01 tolerance. Flag math errors immediately.",
    },
    {
        "agent_name": "service_check",
        "role_description": "Validates each line item against the approved services list. Flags unauthorized, unknown, or over-threshold services.",
        "memory_access": json.dumps(["invoices", "system_knowledge:approved_services", "system_knowledge:approved_vendors"]),
        "decision_methodology": "For each line item: 1. Check if service key matches approved_services. 2. Verify unit_price is within approved max_unit_price. 3. Check vendor is in approved_vendors list. Return per-item verdict with severity: info/warning/critical.",
    },
    {
        "agent_name": "anomaly_check",
        "role_description": "Detects anomalies in invoice data including duplicates, unusual amounts, round number bias, missing fields, and date anomalies.",
        "memory_access": json.dumps(["invoices", "system_knowledge:anomaly_rules"]),
        "decision_methodology": "Check: 1. Duplicate line items. 2. Amounts vs high_amount_threshold. 3. Grand total divisibility by round_number_bias threshold. 4. All required fields present. 5. Invoice date not in future beyond threshold. 6. Currency consistency. Return list of anomalies with severity and reasoning.",
    },
    {
        "agent_name": "pattern_recognition",
        "role_description": "Compares current invoice against vendor history stored in operational_memory to identify unusual patterns, price changes, and new/removed services.",
        "memory_access": json.dumps(["invoices", "operational_memory:vendor_history", "operational_memory:invoice_patterns"]),
        "decision_methodology": "1. Retrieve all approved operational_memory entries for this vendor. 2. Compare grand_total against historical average. 3. Identify new line items not seen before. 4. Identify removed line items. 5. Calculate vendor reliability score from flag_history. 6. Return pattern_insights with trend analysis and recommendations.",
    },
    {
        "agent_name": "decision_agent",
        "role_description": "Makes final verdict on invoice by synthesizing outputs from all prior agents. Uses weighted reasoning to resolve conflicting signals.",
        "memory_access": json.dumps(["event_log", "system_knowledge:decision_weights", "invoices"]),
        "decision_methodology": "1. Read event_log outputs for service_check, anomaly_check, pattern_recognition for this invoice. 2. Load decision_weights from system_knowledge. 3. Score each flag by weight. 4. If any auto_reject_threshold met: verdict=rejected. 5. If cumulative weighted score > 0.7: verdict=flagged. 6. If unresolved critical flags: verdict=requires_human. 7. Otherwise: verdict=approved. Write to final_output.",
    },
    {
        "agent_name": "notifier",
        "role_description": "Generates human-readable notifications for flags and final verdicts. Writes to notifications table.",
        "memory_access": json.dumps(["event_log", "final_output", "invoices"]),
        "decision_methodology": "Two modes: 1. Operational: triggered mid-pipeline when flag raised. Include agent name, flag details, severity, invoice context. 2. Summary: triggered after decision_agent. Include full verdict, all flags, recommendations. Always write to notifications table with appropriate severity.",
    },
]

HISTORICAL_INVOICES = [
    {
        "category": "vendor_history",
        "key": "TechSolutions Inc.",
        "value": {
            "vendor_name": "TechSolutions Inc.",
            "invoice_count": 12,
            "average_grand_total": 2450.00,
            "typical_services": ["SaaS-CRM", "SaaS-ProjectMgmt"],
            "average_line_item_count": 3,
            "last_invoice_date": "2026-03-15",
            "flag_count": 1,
            "reliability_score": 0.92,
        },
    },
    {
        "category": "invoice_patterns",
        "key": "TechSolutions Inc._pattern",
        "value": {
            "vendor_name": "TechSolutions Inc.",
            "typical_invoice_dates": ["first week of month"],
            "price_trend": "stable",
            "monthly_variance": 0.08,
            "common_flags": [],
            "last_updated": "2026-03-15",
        },
    },
    {
        "category": "vendor_history",
        "key": "CloudPlatform Corp.",
        "value": {
            "vendor_name": "CloudPlatform Corp.",
            "invoice_count": 24,
            "average_grand_total": 8750.00,
            "typical_services": ["Cloud-AWS", "Cloud-Storage"],
            "average_line_item_count": 4,
            "last_invoice_date": "2026-04-01",
            "flag_count": 0,
            "reliability_score": 0.98,
        },
    },
]


def seed_database():
    conn = get_connection()
    now = _now()
    try:
        with conn:
            # system_knowledge
            for svc in APPROVED_SERVICES:
                conn.execute(
                    "INSERT OR IGNORE INTO system_knowledge (knowledge_id, category, key, value, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "approved_services", svc["key"], json.dumps(svc["value"]), now, "system"),
                )
            for vend in APPROVED_VENDORS:
                conn.execute(
                    "INSERT OR IGNORE INTO system_knowledge (knowledge_id, category, key, value, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "approved_vendors", vend["key"], json.dumps(vend["value"]), now, "system"),
                )
            for rule in ANOMALY_RULES:
                conn.execute(
                    "INSERT OR IGNORE INTO system_knowledge (knowledge_id, category, key, value, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "anomaly_rules", rule["key"], json.dumps(rule["value"]), now, "system"),
                )
            for dw in DECISION_WEIGHTS:
                conn.execute(
                    "INSERT OR IGNORE INTO system_knowledge (knowledge_id, category, key, value, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "decision_weights", dw["key"], json.dumps(dw["value"]), now, "system"),
                )

            # agent_instructions
            for instr in AGENT_INSTRUCTIONS:
                conn.execute(
                    """INSERT OR IGNORE INTO agent_instructions
                       (instruction_id, agent_name, role_description, memory_access, decision_methodology, version, updated_at, updated_by)
                       VALUES (?,?,?,?,?,1,?,?)""",
                    (
                        str(uuid.uuid4()),
                        instr["agent_name"],
                        instr["role_description"],
                        instr.get("memory_access"),
                        instr.get("decision_methodology"),
                        now,
                        "system",
                    ),
                )

            # operational_memory (pre-approved historical data)
            for hist in HISTORICAL_INVOICES:
                conn.execute(
                    """INSERT OR IGNORE INTO operational_memory
                       (memory_id, category, key, value, suggested_by, approved_by, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()),
                        hist["category"],
                        hist["key"],
                        json.dumps(hist["value"]),
                        "system",
                        "system",
                        "approved",
                        now,
                    ),
                )

        logger.info("Seed data inserted successfully.")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from .schema import init_db
    init_db()
    seed_database()
    print("Database seeded.")
