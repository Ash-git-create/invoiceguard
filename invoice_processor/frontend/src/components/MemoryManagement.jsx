import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api";

const CATEGORY_META = {
  approved_services: { label: "Approved Services", color: "#22c55e" },
  approved_vendors:  { label: "Approved Vendors",  color: "#6366f1" },
  anomaly_rules:     { label: "Anomaly Rules",     color: "#f97316" },
  decision_weights:  { label: "Decision Weights",  color: "#8b5cf6" },
  cost_centers:      { label: "Cost Centers",      color: "#06b6d4" },
  vendor_history:    { label: "Vendor History",    color: "#3b82f6" },
  invoice_patterns:  { label: "Invoice Patterns",  color: "#f59e0b" },
  flag_history:      { label: "Flag History",      color: "#ef4444" },
  agent_suggestions: { label: "Agent Suggestions", color: "#94a3b8" },
};

function CategoryBadge({ category }) {
  const meta = CATEGORY_META[category] || { label: category, color: "var(--text-3)" };
  return (
    <span style={{
      background: `${meta.color}18`,
      color: meta.color,
      border: `1px solid ${meta.color}30`,
      borderRadius: 20, padding: "2px 10px",
      fontSize: 11, fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.4px",
    }}>
      {meta.label}
    </span>
  );
}

function JsonPreview({ value }) {
  const [open, setOpen] = useState(false);
  let parsed = value;
  try { parsed = typeof value === "string" ? JSON.parse(value) : value; } catch (_) {}
  return (
    <div style={{ marginTop: 6 }}>
      <button onClick={() => setOpen(!open)} style={{
        background: "none", border: "none",
        color: "var(--accent)", cursor: "pointer",
        fontSize: 12, fontWeight: 500, fontFamily: "inherit",
        padding: 0, display: "flex", alignItems: "center", gap: 4,
      }}>
        <span style={{ transition: "transform 0.15s", display: "inline-block", transform: open ? "rotate(90deg)" : "none" }}>▸</span>
        {open ? "Hide" : "Show"} value
      </button>
      {open && (
        <pre style={{
          background: "var(--bg-base)", padding: "10px 12px",
          borderRadius: 8, fontSize: 11.5, overflow: "auto",
          color: "var(--text-2)", marginTop: 6,
          border: "1px solid var(--border)", maxHeight: 240,
          lineHeight: 1.5, whiteSpace: "pre-wrap",
        }}>
          {JSON.stringify(parsed, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function MemoryManagement() {
  const [pending, setPending]             = useState([]);
  const [approved, setApproved]           = useState([]);
  const [systemKnowledge, setSystemKnowledge] = useState([]);
  const [agentInstructions, setAgentInstructions] = useState([]);
  const [activeSection, setActiveSection] = useState("pending");
  const [actionMsg, setActionMsg]         = useState(null);
  const [skFilter, setSkFilter]           = useState("all");
  const [loading, setLoading]             = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [p, a, sk, ai] = await Promise.all([
        api.getPendingMemory(), api.getApprovedMemory(),
        api.getSystemKnowledge(), api.getAgentInstructions(),
      ]);
      setPending(p); setApproved(a); setSystemKnowledge(sk); setAgentInstructions(ai);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); const iv = setInterval(refresh, 5000); return () => clearInterval(iv); }, [refresh]);

  async function handleMemoryAction(memoryId, action) {
    setActionMsg(null);
    try {
      if (action === "approve") await api.approveMemory(memoryId, { approved_by: "human" });
      else await api.rejectMemory(memoryId, { rejected_by: "human" });
      setActionMsg({ ok: true, text: `Memory entry ${action}d successfully.` });
      refresh();
    } catch (e) {
      setActionMsg({ ok: false, text: `Error: ${e.message}` });
    }
  }

  if (loading) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "80px 0", color: "var(--text-3)" }}>
      <span className="spinner" />
      <span style={{ fontSize: 14 }}>Loading memory data…</span>
    </div>
  );

  const sections = [
    { id: "pending", label: `Pending Approval`, badge: pending.length },
    { id: "approved", label: "Approved History" },
    { id: "system", label: "System Knowledge" },
    { id: "agents", label: "Agent Instructions" },
  ];

  const skCategories = ["all", ...new Set(systemKnowledge.map((s) => s.category))];
  const filteredSK = skFilter === "all" ? systemKnowledge : systemKnowledge.filter((s) => s.category === skFilter);

  return (
    <div className="fade-in">
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 23, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.4px" }}>
          Memory Management
        </h2>
        <div style={{ color: "var(--text-3)", fontSize: 12.5 }}>
          Manage learned patterns, system knowledge, and agent instructions
        </div>
      </div>

      {/* Section tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {sections.map((s) => {
          const isActive = activeSection === s.id;
          return (
            <button key={s.id} onClick={() => setActiveSection(s.id)} style={{
              background: isActive ? "rgba(99,102,241,0.12)" : "transparent",
              border: `1px solid ${isActive ? "var(--accent)" : "var(--border-light)"}`,
              borderRadius: 20,
              color: isActive ? "var(--accent-2)" : "var(--text-3)",
              padding: "7px 18px", cursor: "pointer",
              fontSize: 13, fontWeight: isActive ? 600 : 400,
              fontFamily: "inherit", transition: "all 0.15s",
              display: "flex", alignItems: "center", gap: 7,
            }}>
              {s.label}
              {s.badge != null && s.badge > 0 && (
                <span style={{
                  background: "#ef4444", color: "#fff",
                  borderRadius: 20, padding: "1px 7px",
                  fontSize: 10.5, fontWeight: 700, lineHeight: 1.4,
                }}>{s.badge}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Status message */}
      {actionMsg && (
        <div className="fade-in" style={{
          marginBottom: 16, padding: "10px 16px", borderRadius: 9, fontSize: 13,
          background: actionMsg.ok ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
          border: `1px solid ${actionMsg.ok ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
          color: actionMsg.ok ? "#4ade80" : "#f87171",
          display: "flex", justifyContent: "space-between",
        }}>
          {actionMsg.text}
          <button onClick={() => setActionMsg(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: 16 }}>×</button>
        </div>
      )}

      {/* ── Pending ──────────────────────────────────────────── */}
      {activeSection === "pending" && (
        <div>
          {pending.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "40px 20px" }}>
              <div style={{ fontSize: 32, marginBottom: 10, opacity: 0.4 }}>✓</div>
              <div style={{ color: "var(--text-2)", fontWeight: 600, fontSize: 15 }}>No pending approvals</div>
              <div style={{ color: "var(--text-3)", fontSize: 13, marginTop: 4 }}>
                The pipeline will suggest memory writes here as it learns from invoices.
              </div>
            </div>
          ) : pending.map((m) => (
            <div key={m.memory_id} className="card" style={{ marginBottom: 12, display: "flex", gap: 16 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
                  <CategoryBadge category={m.category} />
                  <span style={{ color: "var(--text-3)", fontSize: 12 }}>suggested by {m.suggested_by}</span>
                  <span style={{ color: "var(--text-3)", fontSize: 12 }}>· {new Date(m.created_at).toLocaleDateString()}</span>
                </div>
                <div style={{ color: "var(--text-1)", fontWeight: 700, fontSize: 14, marginBottom: 6 }}>{m.key}</div>
                <JsonPreview value={m.value} />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, flexShrink: 0, width: 100 }}>
                <button onClick={() => handleMemoryAction(m.memory_id, "approve")} style={{
                  background: "rgba(34,197,94,0.1)",
                  border: "1px solid rgba(34,197,94,0.4)",
                  borderRadius: 8, color: "#4ade80",
                  padding: "8px 0", cursor: "pointer",
                  fontWeight: 700, fontSize: 13, fontFamily: "inherit",
                  width: "100%",
                }}>✓ Approve</button>
                <button onClick={() => handleMemoryAction(m.memory_id, "reject")} style={{
                  background: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.35)",
                  borderRadius: 8, color: "#f87171",
                  padding: "8px 0", cursor: "pointer",
                  fontWeight: 700, fontSize: 13, fontFamily: "inherit",
                  width: "100%",
                }}>✕ Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Approved history ────────────────────────────────── */}
      {activeSection === "approved" && (
        <div>
          {approved.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "40px 20px" }}>
              <div style={{ color: "var(--text-3)", fontSize: 13 }}>No approved memory entries yet.</div>
            </div>
          ) : approved.map((m) => (
            <div key={m.memory_id} className="card" style={{ marginBottom: 10, padding: "14px 18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                    <CategoryBadge category={m.category} />
                    <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>by {m.suggested_by}</span>
                    <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>→ approved by {m.approved_by}</span>
                    <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>· {new Date(m.created_at).toLocaleDateString()}</span>
                  </div>
                  <div style={{ color: "var(--text-1)", fontWeight: 600, fontSize: 13.5 }}>{m.key}</div>
                  <JsonPreview value={m.value} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── System Knowledge ────────────────────────────────── */}
      {activeSection === "system" && (
        <div>
          <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
            {skCategories.map((c) => {
              const meta = CATEGORY_META[c] || { label: c === "all" ? "All" : c, color: "var(--accent)" };
              const isActive = skFilter === c;
              return (
                <button key={c} onClick={() => setSkFilter(c)} style={{
                  background: isActive ? `${meta.color}18` : "transparent",
                  border: `1px solid ${isActive ? meta.color : "var(--border-light)"}`,
                  borderRadius: 20,
                  color: isActive ? meta.color : "var(--text-3)",
                  padding: "5px 14px", cursor: "pointer",
                  fontSize: 12, fontWeight: isActive ? 600 : 400,
                  fontFamily: "inherit", transition: "all 0.15s",
                }}>
                  {c === "all" ? `All (${systemKnowledge.length})` : (CATEGORY_META[c]?.label || c)}
                </button>
              );
            })}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 10 }}>
            {filteredSK.map((sk) => (
              <div key={sk.knowledge_id} className="card" style={{ padding: "14px 16px" }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                  <CategoryBadge category={sk.category} />
                </div>
                <div style={{ color: "var(--text-1)", fontWeight: 600, fontFamily: "monospace", fontSize: 13 }}>{sk.key}</div>
                <JsonPreview value={sk.value} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Agent Instructions ──────────────────────────────── */}
      {activeSection === "agents" && (
        <div>
          {agentInstructions.map((instr) => (
            <div key={instr.instruction_id} className="card" style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                <div>
                  <h4 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 800, color: "var(--text-1)", textTransform: "capitalize" }}>
                    {instr.agent_name.replace(/_/g, " ")}
                  </h4>
                  <div style={{ color: "var(--text-3)", fontSize: 12 }}>
                    Version {instr.version} · Updated by {instr.updated_by} · {new Date(instr.updated_at).toLocaleString()}
                  </div>
                </div>
                <span style={{
                  background: "rgba(99,102,241,0.12)",
                  color: "var(--accent-2)",
                  border: "1px solid rgba(99,102,241,0.3)",
                  borderRadius: 20, padding: "3px 12px",
                  fontSize: 11, fontWeight: 700,
                }}>v{instr.version}</span>
              </div>

              <div style={{ marginBottom: 12 }}>
                <div className="section-title" style={{ marginBottom: 6 }}>Role</div>
                <div style={{ color: "var(--text-2)", fontSize: 13, lineHeight: 1.6 }}>{instr.role_description}</div>
              </div>

              {instr.memory_access?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>Memory Access</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {(Array.isArray(instr.memory_access) ? instr.memory_access : []).map((t, i) => (
                      <span key={i} style={{
                        background: "var(--bg-card-2)",
                        border: "1px solid var(--border-light)",
                        borderRadius: 6, padding: "2px 10px",
                        fontSize: 11.5, color: "var(--text-2)", fontFamily: "monospace",
                      }}>{t}</span>
                    ))}
                  </div>
                </div>
              )}

              {instr.decision_methodology && (
                <details>
                  <summary style={{ color: "var(--accent)", cursor: "pointer", fontSize: 12.5, fontWeight: 500, outline: "none" }}>
                    Decision Methodology
                  </summary>
                  <div style={{
                    color: "var(--text-2)", fontSize: 12.5, marginTop: 10,
                    lineHeight: 1.7, padding: "10px 14px",
                    background: "var(--bg-card-2)", borderRadius: 8,
                  }}>
                    {instr.decision_methodology}
                  </div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
