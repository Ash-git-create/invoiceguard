import os
import json
import uuid
import logging
from openai import OpenAI

from .base import (
    log_event, log_token_usage, update_queue_status, update_invoice_status,
    get_agent_instructions, check_cost_limit, call_openai_with_retry, _now,
)
from ..database.connection import get_connection

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"


def _extract_pdf(file_path: str) -> str:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts)
    except ImportError:
        raise RuntimeError("pdfplumber not installed. Run: pip install pdfplumber")


def _extract_image(file_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)
    except ImportError:
        raise RuntimeError("pytesseract or Pillow not installed. Run: pip install pytesseract Pillow")


def _extract_docx(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")


def _extract_xml(file_path: str) -> str:
    import xml.etree.ElementTree as ET
    tree = ET.parse(file_path)
    root = tree.getroot()
    parts = []

    def _walk(el, depth=0):
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        val = (el.text or "").strip()
        if val:
            parts.append(f"{'  ' * depth}{tag}: {val}")
        for attr_k, attr_v in el.attrib.items():
            parts.append(f"{'  ' * depth}  @{attr_k}: {attr_v}")
        for child in el:
            _walk(child, depth + 1)

    _walk(root)
    return "\n".join(parts)


def _extract_json(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return json.dumps(data, indent=2)


def _extract_eml(file_path: str) -> str:
    import email
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        msg = email.message_from_file(f)
    parts = [f"Subject: {msg.get('subject', '')}",
             f"From: {msg.get('from', '')}",
             f"Date: {msg.get('date', '')}"]
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                parts.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(parts)


def _extract_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_file(file_path: str) -> tuple[str, str]:
    """Returns (raw_text, file_type)."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return _extract_pdf(file_path), "pdf"
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"):
        return _extract_image(file_path), "image"
    elif ext == ".docx":
        return _extract_docx(file_path), "docx"
    elif ext == ".xml":
        return _extract_xml(file_path), "xml"
    elif ext == ".json":
        return _extract_json(file_path), "json"
    elif ext == ".eml":
        return _extract_eml(file_path), "email"
    elif ext in (".txt", ".csv"):
        return _extract_text(file_path), "text"
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def run(queue_item: dict, client: OpenAI):
    invoice_id = queue_item["invoice_id"]
    queue_id = queue_item["queue_id"]
    conn = get_connection()

    try:
        check_cost_limit(conn, "extractor", invoice_id)

        row = conn.execute("SELECT raw_file_path FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        if not row:
            raise RuntimeError(f"Invoice {invoice_id} not found")
        file_path = row["raw_file_path"]

        with conn:
            update_invoice_status(conn, invoice_id, "extracting")
            update_queue_status(conn, queue_id, "processing")

        raw_text, file_type = extract_file(file_path)

        instr = get_agent_instructions(conn, "extractor")
        system_prompt = (
            f"{instr['role_description']}\n"
            f"Methodology: {instr['decision_methodology']}\n"
            "Return JSON only. No preamble. Schema: "
            '{"raw_text": string, "file_type": string, "metadata": object, "extraction_notes": string}'
        )
        user_prompt = f"File type: {file_type}\nExtracted text:\n{raw_text[:3000]}"

        content, pt, ct = call_openai_with_retry(client, "extractor", MODEL, system_prompt, user_prompt)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"raw_text": raw_text, "file_type": file_type, "metadata": {}, "extraction_notes": "LLM response was not valid JSON; using direct extraction."}

        extracted_data = json.dumps({"stage": "extracted", "raw_text": raw_text, "file_type": file_type, "llm_result": result})

        with conn:
            conn.execute(
                "UPDATE invoices SET extracted_data=?, updated_at=? WHERE invoice_id=?",
                (extracted_data, _now(), invoice_id),
            )
            log_token_usage(conn, "extractor", invoice_id, MODEL, pt, ct)
            log_event(
                conn, invoice_id, "extractor", "extraction_complete",
                f"Extracted {len(raw_text)} characters from {file_type} file.",
                {"file_path": file_path, "file_type": file_type},
                result,
                "success",
            )
            update_queue_status(conn, queue_id, "completed")

        logger.info(f"[extractor] Invoice {invoice_id} extracted successfully.")
        return {"status": "success", "invoice_id": invoice_id, "file_type": file_type}

    except Exception as e:
        logger.error(f"[extractor] Invoice {invoice_id} failed: {e}")
        with conn:
            log_event(
                conn, invoice_id, "extractor", "extraction_failed",
                str(e), {}, {}, "failure",
            )
            update_queue_status(conn, queue_id, "failed")
            update_invoice_status(conn, invoice_id, "failed")
        raise
