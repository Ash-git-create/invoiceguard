import uuid
import json
import logging
import time
from datetime import datetime, timezone
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError

from ..database.connection import get_connection

logger = logging.getLogger(__name__)

COST_PER_TOKEN = {
    "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
    "gpt-4o": {"input": 0.0000025, "output": 0.00001},
}

HARD_COST_LIMIT_USD = 1.50


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_cumulative_cost(conn) -> float:
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM token_usage").fetchone()
    return row[0] if row else 0.0


def check_cost_limit(conn, agent_name: str, invoice_id: str):
    total = get_cumulative_cost(conn)
    if total >= HARD_COST_LIMIT_USD:
        _write_critical_notification(conn, invoice_id, agent_name, total)
        raise RuntimeError(
            f"COST LIMIT EXCEEDED: cumulative spend ${total:.4f} >= ${HARD_COST_LIMIT_USD}. "
            "Pipeline paused. Human approval required."
        )


def _write_critical_notification(conn, invoice_id: str, agent_name: str, total_cost: float):
    conn.execute(
        """INSERT OR IGNORE INTO notifications
           (notification_id, invoice_id, notification_type, title, body, severity, acknowledged, created_at)
           VALUES (?,?,?,?,?,?,0,?)""",
        (
            str(uuid.uuid4()),
            invoice_id,
            "operational",
            "COST LIMIT REACHED - Pipeline Paused",
            f"Cumulative API spend has reached ${total_cost:.4f}, exceeding the ${HARD_COST_LIMIT_USD} hard limit. "
            f"Triggered by agent: {agent_name}. Acknowledge this notification to resume pipeline.",
            "critical",
            _now(),
        ),
    )
    conn.commit()


def log_token_usage(conn, agent_name: str, invoice_id: str, model: str,
                    prompt_tokens: int, completion_tokens: int):
    rates = COST_PER_TOKEN.get(model, {"input": 0.0, "output": 0.0})
    cost = prompt_tokens * rates["input"] + completion_tokens * rates["output"]
    conn.execute(
        """INSERT INTO token_usage
           (usage_id, agent_name, invoice_id, model, prompt_tokens, completion_tokens, cost_usd, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), agent_name, invoice_id, model,
         prompt_tokens, completion_tokens, cost, _now()),
    )
    return cost


def log_event(conn, invoice_id: str, agent_name: str, event_type: str,
              reasoning: str, input_snapshot: dict, output_snapshot: dict, status: str):
    conn.execute(
        """INSERT INTO event_log
           (event_id, invoice_id, agent_name, event_type, reasoning,
            input_snapshot, output_snapshot, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            str(uuid.uuid4()),
            invoice_id,
            agent_name,
            event_type,
            reasoning,
            json.dumps(input_snapshot) if input_snapshot else None,
            json.dumps(output_snapshot) if output_snapshot else None,
            status,
            _now(),
        ),
    )


def update_queue_status(conn, queue_id: str, status: str):
    conn.execute(
        "UPDATE queue SET status=?, updated_at=? WHERE queue_id=?",
        (status, _now(), queue_id),
    )


def update_invoice_status(conn, invoice_id: str, status: str, vendor_name: str = None):
    if vendor_name:
        conn.execute(
            "UPDATE invoices SET current_status=?, vendor_name=?, updated_at=? WHERE invoice_id=?",
            (status, vendor_name, _now(), invoice_id),
        )
    else:
        conn.execute(
            "UPDATE invoices SET current_status=?, updated_at=? WHERE invoice_id=?",
            (status, _now(), invoice_id),
        )


def get_agent_instructions(conn, agent_name: str) -> dict:
    row = conn.execute(
        "SELECT * FROM agent_instructions WHERE agent_name=?", (agent_name,)
    ).fetchone()
    if not row:
        raise RuntimeError(f"No instructions found for agent: {agent_name}")
    return dict(row)


def call_openai_with_retry(client: OpenAI, agent_name: str, model: str,
                           system_prompt: str, user_prompt: str,
                           max_retries: int = 3) -> tuple[str, int, int]:
    """Returns (content, prompt_tokens, completion_tokens). Retries on transient errors."""
    delay = 2
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = response.choices[0].message.content
            pt = response.usage.prompt_tokens
            ct = response.usage.completion_tokens
            return content, pt, ct
        except (RateLimitError, APIConnectionError) as e:
            last_err = e
            if attempt < max_retries:
                logger.warning(f"[{agent_name}] Transient error (attempt {attempt+1}): {e}. Retrying in {delay}s.")
                time.sleep(delay)
                delay *= 2
            else:
                raise RuntimeError(f"[{agent_name}] Max retries exceeded: {e}") from e
        except APIStatusError as e:
            if e.status_code == 429:
                last_err = e
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
            raise RuntimeError(f"[{agent_name}] OpenAI API error: {e}") from e
    raise RuntimeError(f"[{agent_name}] Failed after {max_retries} retries: {last_err}")
