import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api";

const STATUS_COLOR = {
  received:       "#6366f1", extracting:     "#f59e0b",
  formatting:     "#f59e0b", processing:     "#3b82f6",
  flagged:        "#f97316", awaiting_human: "#8b5cf6",
  decision_made:  "#06b6d4", completed:      "#22c55e",
  failed:         "#ef4444", rolled_back:    "#64748b",
};

const SEVERITY_COLOR = { info: "#3b82f6", warning: "#f97316", critical: "#ef4444" };
const VERDICT_CONFIG = {
  approved:       { color: "#22c55e", bg: "rgba(34,197,94,0.08)",   border: "rgba(34,197,94,0.25)",   icon: "✓" },
  flagged:        { color: "#f97316", bg: "rgba(249,115,22,0.08)",  border: "rgba(249,115,22,0.25)",  icon: "⚑" },
  rejected:       { color: "#ef4444", bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.25)",   icon: "✕" },
  requires_human: { color: "#8b5cf6", bg: "rgba(139,92,246,0.08)",  border: "rgba(139,92,246,0.25)",  icon: "?" },
};

const PIPELINE_STAGES = [
  { key: "received",      label: "Received" },
  { key: "extracting",    label: "Extract" },
  { key: "formatting",    label: "Format" },
  { key: "processing",    label: "Process" },
  { key: "decision_made", label: "Decision" },
  { key: "completed",     label: "Done" },
];

const AGENT_ORDER = ["orchestrator","extractor","formatter","service_check",
                      "anomaly_check","pattern_recognition","decision_agent","notifier"];

const AGENT_COLOR = {
  orchestrator:       "#6366f1",
  extractor:          "#f59e0b",
  formatter:          "#f59e0b",
  service_check:      "#3b82f6",
  anomaly_check:      "#ef4444",
  pattern_recognition:"#8b5cf6",
  decision_agent:     "#22c55e",
  notifier:           "#06b6d4",
};

const EV_COLOR = { success: "#22c55e", failure: "#ef4444", flagged: "#f97316", skipped: "#64748b" };

function PipelineStages({ currentStatus }) {
  const stageKeys = PIPELINE_STAGES.map((s) => s.key);
  const currentIdx = stageKeys.indexOf(currentStatus);
  const isFailed = currentStatus === "failed" || currentStatus === "rolled_back";

  return (
    <div className="stage-bar" style={{ marginBottom: 20 }}>
      {PIPELINE_STAGES.map((stage, i) => {
        const done    = currentIdx > i && !isFailed;
        const active  = currentIdx === i && !isFailed;
        const failed  = isFailed && currentIdx >= i;
        const color   = failed ? "#ef4444" : done ? "#22c55e" : active ? "#6366f1" : "var(--border-light)";

        return (
          <div key={stage.key} className="stage-item">
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
              <div className="stage-dot" style={{
                background: done ? "#22c55e" : active ? "rgba(99,102,241,0.15)" : failed ? "rgba(239,68,68,0.15)" : "var(--bg-card-2)",
                borderColor: color,
                color,
              }}>
                {done ? "✓" : failed ? "✕" : i + 1}
              </div>
              <span className="stage-label" style={{ color }}>{stage.label}</span>
            </div>
            {i < PIPELINE_STAGES.length - 1 && (
              <div className="stage-line" style={{
                background: done ? "#22c55e" : "var(--border)",
                marginBottom: 18,
              }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function AgentTimeline({ events }) {
  const byAgent = {};
  for (const ev of events) {
    if (!byAgent[ev.agent_name]) byAgent[ev.agent_name] = [];
    byAgent[ev.agent_name].push(ev);
  }

  return (
    <div>
      {AGENT_ORDER.filter((a) => byAgent[a]).map((agentName) => (
        <AgentRow key={agentName} agentName={agentName} agentEvents={byAgent[agentName]} />
      ))}
    </div>
  );
}

function AgentRow({ agentName, agentEvents }) {
  const [expanded, setExpanded] = useState(false);
  const last = agentEvents[agentEvents.length - 1];
  const dotColor = EV_COLOR[last.status] || "var(--border-light)";
  const agentColor = AGENT_COLOR[agentName] || "var(--accent)";

  return (
    <div className="timeline-item">
      <div className="timeline-dot" style={{ background: dotColor }}>
        <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#fff", display: "block" }} />
      </div>

      <div style={{
        background: "var(--bg-card-2)",
        border: `1px solid ${dotColor}30`,
        borderRadius: 10,
        overflow: "hidden",
      }}>
        {/* Header */}
        <div onClick={() => setExpanded(!expanded)} style={{
          padding: "11px 14px", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          userSelect: "none",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              width: 7, height: 7, borderRadius: "50%",
              background: agentColor, flexShrink: 0,
            }} />
            <span style={{ fontWeight: 700, color: "var(--text-1)", fontSize: 13, textTransform: "capitalize" }}>
              {agentName.replace(/_/g, " ")}
            </span>
            <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>
              {agentEvents.length} event{agentEvents.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{
              background: `${dotColor}18`,
              color: dotColor,
              border: `1px solid ${dotColor}30`,
              borderRadius: 20, padding: "2px 9px",
              fontSize: 10.5, fontWeight: 700, textTransform: "uppercase",
            }}>
              {last.status}
            </span>
            <span style={{ color: "var(--text-3)", fontSize: 11, transition: "transform 0.15s", display: "inline-block", transform: expanded ? "rotate(180deg)" : "none" }}>▾</span>
          </div>
        </div>

        {/* Events */}
        {expanded && agentEvents.map((ev, i) => (
          <div key={ev.event_id} style={{
            padding: "10px 14px",
            borderTop: "1px solid var(--border)",
            background: i % 2 === 0 ? "transparent" : "rgba(6,12,22,0.3)",
          }}>
            <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 5 }}>
              <span style={{ color: "var(--text-3)", fontSize: 11 }}>{new Date(ev.created_at).toLocaleTimeString()}</span>
              <span style={{ color: "var(--text-3)", fontSize: 11 }}>·</span>
              <span style={{ color: "var(--text-2)", fontSize: 11.5, fontFamily: "monospace" }}>{ev.event_type}</span>
            </div>
            {ev.reasoning && (
              <div style={{ color: "var(--text-2)", fontSize: 13, lineHeight: 1.5, marginBottom: 6 }}>{ev.reasoning}</div>
            )}
            {ev.output_snapshot && (
              <details style={{ marginTop: 4 }}>
                <summary style={{ color: "var(--accent)", cursor: "pointer", fontSize: 12, fontWeight: 500 }}>
                  View output snapshot
                </summary>
                <pre style={{
                  background: "var(--bg-base)", padding: 12, borderRadius: 7,
                  fontSize: 11, overflow: "auto", color: "var(--text-2)",
                  marginTop: 8, lineHeight: 1.5, maxHeight: 300,
                }}>
                  {JSON.stringify(ev.output_snapshot, null, 2)}
                </pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "7px 0", borderBottom: "1px solid rgba(26,45,69,0.5)",
    }}>
      <span style={{ color: "var(--text-3)", fontSize: 13 }}>{label}</span>
      <span style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function ActionBtn({ label, color, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: hover ? `${color}20` : "transparent",
        border: `1px solid ${color}60`,
        borderRadius: 9, color,
        padding: "9px 16px", cursor: "pointer",
        fontWeight: 600, fontSize: 13,
        textAlign: "left", transition: "all 0.15s",
        fontFamily: "inherit", width: "100%",
      }}>
      {label}
    </button>
  );
}

export default function InvoiceDetail({ invoiceId, onBack }) {
  const [invoice, setInvoice]   = useState(null);
  const [loading, setLoading]   = useState(true);
  const [actionMsg, setActionMsg] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setInvoice(await api.getInvoice(invoiceId));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [invoiceId]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 3000);
    return () => clearInterval(iv);
  }, [refresh]);

  async function doAction(action, extraData = {}) {
    setActionMsg(null);
    try {
      let res;
      if (action === "approve")  res = await api.approveFlag(invoiceId, { performed_by: "human", ...extraData });
      if (action === "reject")   res = await api.rejectFlag(invoiceId,  { performed_by: "human", ...extraData });
      if (action === "rollback") res = await api.rollback(invoiceId,    { performed_by: "human" });
      if (action === "rerun")    res = await api.rerun(invoiceId,       { performed_by: "human", force: extraData.force });
      setActionMsg({ ok: true, text: `"${action}" action completed — status: ${res.status}` });
      setTimeout(refresh, 600);
    } catch (e) {
      setActionMsg({ ok: false, text: `Error: ${e.message}` });
    }
  }

  if (loading) return <div style={{ color: "var(--text-3)", padding: "60px 0", textAlign: "center" }}>Loading invoice…</div>;
  if (!invoice) return <div style={{ color: "var(--danger)", padding: 40 }}>Invoice not found.</div>;

  const inv          = invoice;
  const data         = inv.extracted_data?.data || {};
  const flags        = inv.final_output?.flags || [];
  const recommendations = inv.final_output?.recommendations || [];
  const verdict      = inv.final_output?.verdict;
  const vc           = VERDICT_CONFIG[verdict];
  const statusColor  = STATUS_COLOR[inv.current_status] || "#64748b";

  return (
    <div className="fade-in">
      {/* ── Back + Header ─────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button onClick={onBack} className="btn btn-ghost" style={{ padding: "7px 14px" }}>
            ← Back
          </button>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.3px" }}>
              {inv.vendor_name || "Unknown Vendor"}
            </h2>
            <div style={{ color: "var(--text-3)", fontSize: 11.5, fontFamily: "monospace", marginTop: 2 }}>
              {invoiceId}
            </div>
          </div>
        </div>

        <span style={{
          background: `${statusColor}18`,
          color: statusColor,
          border: `1px solid ${statusColor}40`,
          borderRadius: 20, padding: "5px 16px",
          fontSize: 12.5, fontWeight: 700, textTransform: "uppercase",
        }}>
          {inv.current_status?.replace(/_/g, " ")}
        </span>
      </div>

      {/* ── Pipeline stages ───────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20, padding: "16px 20px 8px" }}>
        <div className="section-title" style={{ marginBottom: 10 }}>Pipeline Progress</div>
        <PipelineStages currentStatus={inv.current_status} />
      </div>

      {/* ── Verdict banner ────────────────────────────────── */}
      {vc && (
        <div className="verdict-banner fade-in" style={{
          background: vc.bg,
          borderColor: vc.border,
        }}>
          <div style={{
            width: 44, height: 44, borderRadius: "50%",
            background: `${vc.color}20`,
            border: `2px solid ${vc.color}50`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 20, fontWeight: 800, color: vc.color, flexShrink: 0,
          }}>
            {vc.icon}
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: vc.color, textTransform: "uppercase", letterSpacing: "0.5px" }}>
              {verdict?.replace(/_/g, " ")}
            </div>
            {inv.final_output?.summary && (
              <div style={{ color: "var(--text-2)", fontSize: 13, marginTop: 3 }}>{inv.final_output.summary}</div>
            )}
          </div>
          {inv.final_output?.confidence != null && (
            <div style={{ marginLeft: "auto", textAlign: "right" }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: vc.color }}>
                {Math.round(inv.final_output.confidence * 100)}%
              </div>
              <div style={{ color: "var(--text-3)", fontSize: 11, textTransform: "uppercase" }}>Confidence</div>
            </div>
          )}
        </div>
      )}

      {/* ── Main grid ─────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Invoice Summary */}
          <div className="card">
            <div className="section-title">Invoice Summary</div>
            {data.vendor_name    && <SummaryRow label="Vendor"        value={data.vendor_name} />}
            {data.invoice_number && <SummaryRow label="Invoice #"     value={data.invoice_number} />}
            {data.invoice_date   && <SummaryRow label="Invoice Date"  value={data.invoice_date} />}
            {data.due_date       && <SummaryRow label="Due Date"      value={data.due_date} />}
            {data.payment_terms  && <SummaryRow label="Terms"         value={data.payment_terms} />}
            {data.currency       && <SummaryRow label="Currency"      value={data.currency} />}
            {data.grand_total != null && (
              <div style={{ marginTop: 12, padding: "12px 0 4px" }}>
                <div style={{ color: "var(--text-3)", fontSize: 12, marginBottom: 4 }}>Grand Total</div>
                <div style={{ fontSize: 30, fontWeight: 900, color: "var(--text-1)", letterSpacing: "-1px" }}>
                  {data.currency || "USD"} {Number(data.grand_total).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
            )}
            {data.math_valid != null && (
              <div style={{
                marginTop: 12, padding: "8px 12px", borderRadius: 8,
                background: data.math_valid ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
                border: `1px solid ${data.math_valid ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`,
                color: data.math_valid ? "#4ade80" : "#f87171",
                fontSize: 13, fontWeight: 500,
              }}>
                {data.math_valid ? "✓ Math checks passed" : `✕ ${data.math_notes}`}
              </div>
            )}
          </div>

          {/* Line Items */}
          {data.line_items?.length > 0 && (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px 12px" }}>
                <div className="section-title" style={{ marginBottom: 0 }}>Line Items</div>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    {["Description", "Qty", "Unit Price", "Total"].map((h) => (
                      <th key={h} style={{ fontSize: 10.5 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.line_items.map((item, i) => (
                    <tr key={i} style={{ cursor: "default" }}>
                      <td style={{ color: "var(--text-1)", fontSize: 13 }}>{item.description}</td>
                      <td style={{ color: "var(--text-2)", fontSize: 13 }}>{item.quantity}</td>
                      <td style={{ color: "var(--text-2)", fontSize: 13, fontFamily: "monospace" }}>{Number(item.unit_price).toFixed(2)}</td>
                      <td style={{ color: "var(--text-1)", fontWeight: 600, fontSize: 13, fontFamily: "monospace" }}>{Number(item.total).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ padding: "10px 20px 14px", borderTop: "1px solid var(--border)" }}>
                {[["Subtotal", data.subtotal], ["Tax", data.tax], ["Grand Total", data.grand_total]].map(([label, val], i) => (
                  <div key={label} style={{
                    display: "flex", justifyContent: "space-between",
                    padding: "4px 0",
                    fontWeight: i === 2 ? 800 : 400,
                    color: i === 2 ? "var(--text-1)" : "var(--text-2)",
                    fontSize: i === 2 ? 14 : 13,
                    borderTop: i === 2 ? "1px solid var(--border)" : "none",
                    marginTop: i === 2 ? 4 : 0,
                  }}>
                    <span>{label}</span>
                    <span style={{ fontFamily: "monospace" }}>{Number(val || 0).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div className="card">
              <div className="section-title">Recommendations</div>
              {recommendations.map((r, i) => (
                <div key={i} style={{
                  display: "flex", gap: 10, alignItems: "flex-start",
                  padding: "6px 0", borderBottom: "1px solid rgba(26,45,69,0.4)",
                  color: "var(--text-2)", fontSize: 13,
                }}>
                  <span style={{ color: "var(--accent)", fontWeight: 700, flexShrink: 0 }}>→</span>
                  {r}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Flags */}
          {flags.length > 0 && (
            <div className="card">
              <div className="section-title">Flags ({flags.length})</div>
              {flags.map((flag, i) => {
                const fc = SEVERITY_COLOR[flag.severity] || "#64748b";
                return (
                  <div key={i} style={{
                    background: `${fc}0c`,
                    border: `1px solid ${fc}30`,
                    borderLeft: `3px solid ${fc}`,
                    borderRadius: 8,
                    padding: "10px 14px",
                    marginBottom: 8,
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ color: "var(--text-2)", fontSize: 11.5, fontWeight: 600 }}>{flag.agent?.replace(/_/g," ")}</span>
                      <span style={{
                        background: `${fc}20`, color: fc,
                        borderRadius: 20, padding: "1px 8px",
                        fontSize: 10.5, fontWeight: 700, textTransform: "uppercase",
                      }}>{flag.severity}</span>
                    </div>
                    <div style={{ color: "var(--text-1)", fontSize: 13 }}>{flag.reason}</div>
                    {flag.item && <div style={{ color: "var(--text-3)", fontSize: 12, marginTop: 3 }}>→ {flag.item}</div>}
                  </div>
                );
              })}
            </div>
          )}

          {/* Human Actions */}
          <div className="card">
            <div className="section-title">Human Actions</div>

            {actionMsg && (
              <div className="fade-in" style={{
                marginBottom: 12, padding: "9px 14px", borderRadius: 8,
                background: actionMsg.ok ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
                border: `1px solid ${actionMsg.ok ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
                color: actionMsg.ok ? "#4ade80" : "#f87171",
                fontSize: 13,
              }}>
                {actionMsg.text}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <ActionBtn label="✓ Approve Flag"       color="#22c55e" onClick={() => doAction("approve")} />
              <ActionBtn label="✕ Reject Flag"        color="#ef4444" onClick={() => doAction("reject")} />
              <ActionBtn label="↩ Rollback Invoice"   color="#f97316" onClick={() => doAction("rollback")} />
              <ActionBtn label="↺ Rerun Pipeline"     color="#6366f1" onClick={() => doAction("rerun", { force: false })} />
              <ActionBtn label="↺ Force Rerun"        color="#8b5cf6" onClick={() => doAction("rerun", { force: true })} />
            </div>
          </div>

          {/* Agent Timeline */}
          <div className="card">
            <div className="section-title">Agent Timeline</div>
            {inv.events?.length > 0
              ? <AgentTimeline events={inv.events} />
              : <div style={{ color: "var(--text-3)", fontSize: 13 }}>No events yet — pipeline is queued.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
