import React, { useState, useEffect, useCallback } from "react";
import PipelineMonitor from "./components/PipelineMonitor";
import InvoiceDetail from "./components/InvoiceDetail";
import ObservabilityDashboard from "./components/ObservabilityDashboard";
import MemoryManagement from "./components/MemoryManagement";
import ArchitectureDiagram from "./components/ArchitectureDiagram";
import { api } from "./api";

export const STATUS_COLOR = {
  received:      "#6366f1",
  extracting:    "#f59e0b",
  formatting:    "#f59e0b",
  processing:    "#3b82f6",
  flagged:       "#f97316",
  awaiting_human:"#8b5cf6",
  decision_made: "#06b6d4",
  completed:     "#22c55e",
  failed:        "#ef4444",
  rolled_back:   "#64748b",
};

const TABS = [
  { id: "pipeline",      label: "Pipeline",      icon: "⬡" },
  { id: "observability", label: "Observability",  icon: "◈" },
  { id: "memory",        label: "Memory",         icon: "◉" },
  { id: "architecture",  label: "Architecture",   icon: "◫" },
];

export default function App() {
  const [activeTab, setActiveTab]               = useState("pipeline");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState(null);
  const [pendingCount, setPendingCount]         = useState(0);

  const fetchPendingCount = useCallback(async () => {
    try {
      const data = await api.getPendingNotifications();
      setPendingCount(data.length);
    } catch (_) {}
  }, []);

  useEffect(() => {
    fetchPendingCount();
    const iv = setInterval(fetchPendingCount, 5000);
    return () => clearInterval(iv);
  }, [fetchPendingCount]);

  function handleSelectInvoice(id) {
    setSelectedInvoiceId(id);
    setActiveTab("detail");
  }

  function handleBack() {
    setSelectedInvoiceId(null);
    setActiveTab("pipeline");
  }

  const showingDetail = activeTab === "detail" && selectedInvoiceId;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
      {/* ── Header ─────────────────────────────────────────── */}
      <header style={{
        background: "rgba(12,21,36,0.95)",
        borderBottom: "1px solid var(--border)",
        backdropFilter: "blur(12px)",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}>
        <div style={{ maxWidth: 1440, margin: "0 auto", padding: "0 28px" }}>
          {/* Logo row */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 14, paddingBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              {/* Logo */}
              <div style={{
                width: 36, height: 36,
                background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                borderRadius: 10,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 900, fontSize: 14, color: "#fff",
                boxShadow: "0 4px 14px rgba(99,102,241,0.4)",
                letterSpacing: "-0.5px",
              }}>IG</div>

              <div>
                <div style={{ fontWeight: 800, fontSize: 17, color: "var(--text-1)", letterSpacing: "-0.3px", lineHeight: 1 }}>
                  InvoiceGuard
                </div>
                <div style={{ color: "var(--text-3)", fontSize: 11, marginTop: 2, letterSpacing: "0.4px" }}>
                  MULTI-AGENT PIPELINE
                </div>
              </div>
            </div>

            {/* Right side: live indicator + alerts */}
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="pulse-dot active" style={{ background: "#22c55e" }} />
                <span style={{ color: "var(--text-3)", fontSize: 12 }}>Live</span>
              </div>

              {pendingCount > 0 && (
                <button
                  onClick={() => setActiveTab("pipeline")}
                  style={{
                    background: "rgba(239,68,68,0.15)",
                    border: "1px solid rgba(239,68,68,0.4)",
                    borderRadius: 20,
                    padding: "5px 14px",
                    color: "#fca5a5",
                    fontSize: 12, fontWeight: 700,
                    cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 6,
                    fontFamily: "inherit",
                  }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} />
                  {pendingCount} alert{pendingCount !== 1 ? "s" : ""}
                </button>
              )}
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 2 }}>
            {showingDetail && (
              <button onClick={handleBack} style={{
                padding: "8px 16px",
                background: "none", border: "none",
                borderBottom: "2px solid var(--accent)",
                color: "var(--accent)",
                cursor: "pointer", fontSize: 13, fontWeight: 600,
                fontFamily: "inherit",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                ← Detail
              </button>
            )}
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button key={tab.id}
                  onClick={() => { setActiveTab(tab.id); if (tab.id !== "detail") setSelectedInvoiceId(null); }}
                  style={{
                    padding: "9px 18px",
                    background: "none", border: "none",
                    borderBottom: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                    color: isActive ? "var(--accent-2)" : "var(--text-3)",
                    cursor: "pointer", fontSize: 13,
                    fontWeight: isActive ? 600 : 400,
                    fontFamily: "inherit",
                    transition: "all 0.15s",
                    display: "flex", alignItems: "center", gap: 6,
                  }}>
                  <span style={{ fontSize: 14, opacity: isActive ? 1 : 0.7 }}>{tab.icon}</span>
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      {/* ── Content ────────────────────────────────────────── */}
      <main style={{ maxWidth: 1440, margin: "0 auto", padding: "28px 28px 60px" }}>
        {activeTab === "pipeline" && <PipelineMonitor onSelectInvoice={handleSelectInvoice} />}
        {showingDetail && <InvoiceDetail invoiceId={selectedInvoiceId} onBack={handleBack} />}
        {activeTab === "observability" && <ObservabilityDashboard />}
        {activeTab === "memory"        && <MemoryManagement />}
        {activeTab === "architecture"  && <ArchitectureDiagram />}
      </main>
    </div>
  );
}
