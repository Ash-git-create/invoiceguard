import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api";

const STATUS_COLOR = {
  received:       "#6366f1", extracting:    "#f59e0b",
  formatting:     "#f59e0b", processing:    "#3b82f6",
  flagged:        "#f97316", awaiting_human:"#8b5cf6",
  decision_made:  "#06b6d4", completed:     "#22c55e",
  failed:         "#ef4444", rolled_back:   "#64748b",
};

const ACTIVE_STATUSES = ["received","extracting","formatting","processing","decision_made"];

function elapsed(createdAt) {
  if (!createdAt) return "—";
  const d = (Date.now() - new Date(createdAt).getTime()) / 1000;
  if (d < 60) return `${Math.floor(d)}s`;
  if (d < 3600) return `${Math.floor(d / 60)}m ${Math.floor(d % 60)}s`;
  return `${Math.floor(d / 3600)}h ${Math.floor((d % 3600) / 60)}m`;
}

function StatusBadge({ status }) {
  const color = STATUS_COLOR[status] || "#64748b";
  const isActive = ACTIVE_STATUSES.includes(status);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        className={`pulse-dot${isActive ? " active" : ""}`}
        style={{ background: color }}
      />
      <span style={{
        background: `${color}18`,
        color,
        border: `1px solid ${color}38`,
        borderRadius: 20,
        padding: "2px 10px",
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.4px",
      }}>
        {status?.replace(/_/g, " ")}
      </span>
    </span>
  );
}

function StatCard({ label, value, color = "var(--text-1)", borderColor }) {
  return (
    <div className="stat-card" style={{ borderTop: `3px solid ${borderColor || "var(--border)"}` }}>
      <div className="stat-value" style={{ color }}>{value ?? "—"}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function PipelineMonitor({ onSelectInvoice }) {
  const [invoices, setInvoices]     = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [uploading, setUploading]   = useState(false);
  const [uploadMsg, setUploadMsg]   = useState(null);
  const [filter, setFilter]         = useState("all");
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef();

  const refresh = useCallback(async () => {
    try {
      const [invs, notifs] = await Promise.all([api.listInvoices(), api.getPendingNotifications()]);
      setInvoices(invs);
      setNotifications(notifs);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 3000);
    return () => clearInterval(iv);
  }, [refresh]);

  async function handleUploadFile(file) {
    if (!file) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const result = await api.uploadInvoice(file);
      setUploadMsg({ ok: true, text: `Invoice ${result.invoice_id?.slice(0, 8)}… queued. Pipeline running.` });
      setTimeout(refresh, 600);
    } catch (err) {
      setUploadMsg({ ok: false, text: `Upload failed: ${err.message}` });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function handleFileInput(e) { handleUploadFile(e.target.files?.[0]); }
  function handleDragOver(e)  { e.preventDefault(); setIsDragging(true); }
  function handleDragLeave()  { setIsDragging(false); }
  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    handleUploadFile(e.dataTransfer.files?.[0]);
  }

  async function handleAcknowledge(id) {
    await api.acknowledgeNotification(id);
    refresh();
  }

  const filtered   = filter === "all" ? invoices : invoices.filter((i) => i.current_status === filter);
  const activeCount    = invoices.filter((i) => ACTIVE_STATUSES.includes(i.current_status)).length;
  const flaggedCount   = invoices.filter((i) => ["flagged","awaiting_human"].includes(i.current_status)).length;
  const completedCount = invoices.filter((i) => i.current_status === "completed").length;
  const failedCount    = invoices.filter((i) => i.current_status === "failed").length;

  const FILTERS = [
    { key: "all",           label: `All (${invoices.length})` },
    { key: "processing",    label: "Processing" },
    { key: "flagged",       label: "Flagged" },
    { key: "awaiting_human",label: "Awaiting Human" },
    { key: "completed",     label: "Completed" },
    { key: "failed",        label: "Failed" },
  ];

  return (
    <div className="fade-in">
      {/* ── Notifications ─────────────────────────────────── */}
      {notifications.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {notifications.slice(0, 3).map((n) => (
            <div key={n.notification_id}
              className={`toast toast-${n.severity}`}>
              <div style={{ flex: 1 }}>
                <div style={{
                  fontWeight: 700, fontSize: 13.5,
                  color: n.severity === "critical" ? "#fca5a5" : n.severity === "warning" ? "#fdba74" : "#93c5fd",
                  marginBottom: 2,
                }}>
                  {n.title}
                </div>
                <div style={{ color: "var(--text-2)", fontSize: 12.5 }}>{n.body}</div>
              </div>
              <button onClick={() => handleAcknowledge(n.notification_id)} style={{
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: 7, color: "var(--text-2)",
                padding: "5px 13px", cursor: "pointer",
                fontSize: 12, fontWeight: 500,
                whiteSpace: "nowrap", fontFamily: "inherit",
              }}>Dismiss</button>
            </div>
          ))}
          {notifications.length > 3 && (
            <div style={{ color: "var(--text-3)", fontSize: 12.5, textAlign: "center", marginTop: 4 }}>
              +{notifications.length - 3} more alerts
            </div>
          )}
        </div>
      )}

      {/* ── Page title ────────────────────────────────────── */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 23, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.4px" }}>
          Pipeline Monitor
        </h2>
        <div style={{ color: "var(--text-3)", fontSize: 12.5 }}>
          {activeCount > 0
            ? <><span className="pulse-dot active" style={{ background: "#22c55e", marginRight: 6 }} /> {activeCount} processing now · </> : null}
          {invoices.length} total invoices · auto-refresh every 3s
        </div>
      </div>

      {/* ── Stat cards ────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 20 }}>
        <StatCard label="Total"     value={invoices.length}  borderColor="var(--accent)" />
        <StatCard label="Active"    value={activeCount}      color="#3b82f6"   borderColor="#3b82f6" />
        <StatCard label="Flagged"   value={flaggedCount}     color="#f97316"   borderColor="#f97316" />
        <StatCard label="Completed" value={completedCount}   color="#22c55e"   borderColor="#22c55e" />
        <StatCard label="Failed"    value={failedCount}      color="#ef4444"   borderColor="#ef4444" />
      </div>

      {/* ── Drop zone ─────────────────────────────────────── */}
      <div
        className={`drop-zone${isDragging ? " dragging" : ""}`}
        style={{ marginBottom: 20 }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !uploading && fileRef.current?.click()}
      >
        {uploading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <span className="spinner" />
            <span style={{ color: "var(--text-2)", fontSize: 14 }}>Uploading…</span>
          </div>
        ) : (
          <>
            <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.6 }}>⬆</div>
            <div style={{ color: "var(--text-1)", fontWeight: 600, fontSize: 14.5, marginBottom: 4 }}>
              {isDragging ? "Release to upload" : "Drop invoice here or click to browse"}
            </div>
            <div style={{ color: "var(--text-3)", fontSize: 12 }}>
              PDF · PNG · JPG · DOCX · XML · JSON · EML · TXT
            </div>
          </>
        )}
        <input ref={fileRef} type="file" style={{ display: "none" }}
          accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp,.gif,.docx,.xml,.json,.eml,.txt"
          onChange={handleFileInput} />
      </div>

      {/* Upload status message */}
      {uploadMsg && (
        <div className="fade-in" style={{
          marginBottom: 14, padding: "10px 16px", borderRadius: 9,
          background: uploadMsg.ok ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
          border: `1px solid ${uploadMsg.ok ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
          color: uploadMsg.ok ? "#4ade80" : "#f87171",
          fontSize: 13, fontWeight: 500,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          {uploadMsg.text}
          <button onClick={() => setUploadMsg(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", padding: 0, fontSize: 16, lineHeight: 1 }}>×</button>
        </div>
      )}

      {/* ── Filter pills ──────────────────────────────────── */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {FILTERS.map(({ key, label }) => (
          <button key={key} onClick={() => setFilter(key)} style={{
            background: filter === key ? "rgba(99,102,241,0.15)" : "transparent",
            border: `1px solid ${filter === key ? "var(--accent)" : "var(--border-light)"}`,
            borderRadius: 20,
            color: filter === key ? "var(--accent-2)" : "var(--text-3)",
            padding: "5px 14px", cursor: "pointer",
            fontSize: 12, fontWeight: filter === key ? 600 : 400,
            fontFamily: "inherit", transition: "all 0.15s",
          }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Invoice table ─────────────────────────────────── */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {filtered.length === 0 ? (
          <div style={{ padding: "60px 20px", textAlign: "center" }}>
            <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.3 }}>📄</div>
            <div style={{ color: "var(--text-2)", fontWeight: 600, fontSize: 15 }}>No invoices found</div>
            <div style={{ color: "var(--text-3)", fontSize: 13, marginTop: 4 }}>
              {invoices.length === 0 ? "Upload an invoice above to start the pipeline." : "No invoices match the current filter."}
            </div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                {["Invoice ID", "Vendor", "Status", "Flags", "Elapsed", "Created"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((inv) => (
                <tr key={inv.invoice_id} onClick={() => onSelectInvoice(inv.invoice_id)}>
                  <td style={{ fontFamily: "monospace", fontSize: 12.5, color: "var(--text-3)" }}>
                    {inv.invoice_id.slice(0, 8)}…
                  </td>
                  <td style={{ fontWeight: 600, color: "var(--text-1)", fontSize: 13.5 }}>
                    {inv.vendor_name || <span style={{ color: "var(--text-3)", fontStyle: "italic", fontWeight: 400 }}>Identifying…</span>}
                  </td>
                  <td><StatusBadge status={inv.current_status} /></td>
                  <td>
                    {inv.flag_count > 0 ? (
                      <span style={{
                        background: "rgba(239,68,68,0.1)",
                        color: "#f87171",
                        border: "1px solid rgba(239,68,68,0.25)",
                        borderRadius: 20, padding: "2px 10px",
                        fontSize: 12, fontWeight: 700,
                      }}>
                        ⚑ {inv.flag_count}
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-3)", fontSize: 12 }}>—</span>
                    )}
                  </td>
                  <td style={{ color: "var(--text-2)", fontSize: 12.5 }}>{elapsed(inv.created_at)}</td>
                  <td style={{ color: "var(--text-3)", fontSize: 12 }}>
                    {new Date(inv.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
