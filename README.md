# InvoiceGuard

A multi-agent system that processes invoices through a pipeline of specialized AI agents, flags anything suspicious, and keeps humans in the loop for final decisions. Built because manually reviewing invoices is tedious and error-prone — and the errors tend to be expensive.

---

## What it does

You upload an invoice (PDF, image, Word doc, XML, email, plain text), and the system:

1. Extracts the raw text using the right parser for the file type
2. Structures it into a validated JSON format and checks the math
3. Runs three checks in parallel — whether the services are approved, whether anything looks anomalous, and whether the amounts match the vendor's historical patterns
4. Synthesizes all of that into a final verdict: **approved**, **flagged**, **rejected**, or **requires human review**
5. Logs every decision with a full audit trail you can't modify retroactively

If anything looks off at any stage, it fires a notification and waits for a human to weigh in before moving on.

---

## Why I built it this way

**Why multiple agents instead of one big prompt?**
Each agent has a narrow job and its own context window. A single "analyze this invoice" prompt gets confused and inconsistent as invoices get complex. Separate agents for math validation, service checking, anomaly detection, and pattern recognition each stay focused and their outputs are independently auditable.

**Why run three agents in parallel?**
Service checking, anomaly detection, and pattern recognition don't depend on each other's results. Running them sequentially would roughly triple the latency for no reason. The decision agent waits for all three and synthesizes.

**Why SQLite instead of Postgres?**
Single-process deployment, no ops overhead, WAL mode handles concurrent reads fine. If this needed to scale horizontally you'd swap the connection layer, but for a team's invoice processing that's premature. The schema is in one place, migrations are explicit.

**Why gpt-4o-mini for most agents?**
Each agent makes a very structured request and expects a very structured response. The complexity ceiling is low — you're asking "is this service name in this list?" not "write me an essay." gpt-4o-mini is fast and cheap for that. gpt-4o only runs on the decision agent where you need it to reason across conflicting signals from multiple agents.

**Why immutable audit logs?**
SQLite triggers prevent any UPDATE or DELETE on the event_log table. This isn't a nice-to-have — if you're using this for anything finance-adjacent, you need to be able to prove what the system decided and why, without worrying that someone cleaned it up after the fact.

**Why the $1.50 cost limit?**
Hard stop on cumulative API spend. It's configurable, but it defaults to something low so you notice if something is wrong (runaway retry loops, unexpectedly large invoices) before it costs you.

---

## Architecture

```
Upload → Extractor → Formatter → ┌─ Service Check    ─┐
                                  ├─ Anomaly Check    ─┤ → Decision Agent → Notifier
                                  └─ Pattern Check    ─┘

           (sequential)                 (parallel)          (sequential)
```

The orchestrator runs this pipeline in a background thread after the upload returns 202. The frontend polls for status updates every 3 seconds.

**8 agents total:**
- `extractor` — reads the file, no LLM involved, just file parsing
- `formatter` — sends raw text to gpt-4o-mini, gets back structured JSON with math validation
- `service_check` — validates each line item against your approved services catalog
- `anomaly_check` — looks for duplicates, round numbers, future dates, missing fields
- `pattern_recognition` — compares against the vendor's invoice history from memory
- `decision_agent` — gpt-4o synthesizes all flags with configurable weights
- `notifier` — generates human-readable alerts mid-pipeline and at completion
- `orchestrator` — no LLM, pure coordination logic

---

## Running it locally

**Requirements:** Python 3.11+, Node 18+, an OpenAI API key.

```bash
# Clone and install Python deps
git clone https://github.com/YOUR_USERNAME/invoiceguard.git
cd invoiceguard
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start the backend (auto-creates and seeds the database)
python run_backend.py

# In a second terminal, start the frontend
cd invoice_processor/frontend
npm install
npm start
```

Open http://localhost:3000. The backend runs on port 5000.

---

## Trying it out

Three sample invoices are included in `sample_invoices/`:

**`clean_invoice.txt`** — TechSolutions Inc., two approved services, math checks out. Should complete as `approved` in a few seconds.

**`unknown_service_invoice.txt`** — "ShadyVendor LLC" with services like "Premium Data Harvesting Service." Four critical flags from service_check, rejected immediately. Good for seeing what the flag UI looks like.

**`math_anomaly_invoice.xml`** — CloudPlatform Corp, valid vendor, but the line items don't add up to the subtotal. Also has a duplicate line item and a suspiciously round grand total. Triggers math, duplicate, and round-number flags. Usually ends up as `requires_human`.

Upload them through the drag-and-drop zone in the Pipeline Monitor tab, then click the invoice row to see the full agent trace.

---

## The human-in-the-loop part

When an invoice is flagged or rejected, it sits in `awaiting_human` status. A reviewer can:

- **Approve the flag** — overrides the verdict to completed. Importantly, this writes a record to operational memory so the decision agent knows about the override the next time it sees an invoice from this vendor. That feedback loop gradually adjusts how hard the agent flags certain issues for trusted vendors.
- **Reject the flag** — confirms the rejection. Also written to memory.
- **Rollback** — marks the invoice as rolled_back and logs every stage being undone (the saga pattern). The event log is immutable so the history stays intact, but the invoice status reverts.
- **Rerun** — starts the whole pipeline again from scratch. Useful after updating agent instructions or adding a new approved service.

---

## Memory system

There are two kinds of memory:

**System knowledge** is the static catalog — approved services with max prices, approved vendors with monthly spend limits, anomaly thresholds, decision weights. This is seeded on startup and doesn't change unless you update it manually.

**Operational memory** is learned. The orchestrator automatically suggests vendor history updates after each invoice (which services were billed, at what amounts). These suggestions sit in a pending queue — you can see them in the Memory tab and approve or reject each one. Only approved entries feed back into the pattern recognition agent.

The flag history from human overrides is the third layer: written automatically when a human approves or rejects a flag, immediately available to the decision agent on the next run.

---

## Cost tracking

Every LLM call logs token usage to a `token_usage` table. The Observability tab shows cumulative spend, per-agent breakdown, and a daily cost trend. At $1.50 cumulative (configurable), all LLM calls stop and a critical notification fires. For context, a typical invoice costs around $0.003–$0.008 to process end-to-end.

---

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The test suite covers Pydantic schema validation for all five agent response types, the base utilities (cost tracking, immutable event log enforcement, retry logic), and the API endpoints (upload, list, detail, feedback loop, memory).

---

## Supported file types

| Format | Method |
|--------|--------|
| PDF | pdfplumber, all pages |
| PNG/JPG/TIFF/BMP/GIF | pytesseract OCR |
| DOCX | python-docx paragraph extraction |
| XML | ElementTree recursive walk |
| JSON | validated and pretty-printed |
| EML | email headers + plain text body |
| TXT | direct read |

---

## Tech stack

**Backend:** Flask 3, Flask-Limiter, SQLite (WAL mode), OpenAI Python SDK, Pydantic v2, pdfplumber, pytesseract  
**Frontend:** React 18, react-scripts (no UI library, all custom CSS)  
**Testing:** pytest, pytest-mock
