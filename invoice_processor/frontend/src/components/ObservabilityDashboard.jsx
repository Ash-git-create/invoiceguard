import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api";

const SEVERITY_COLOR = { critical: "#ef4444", warning: "#f97316", info: "#3b82f6" };

function MetricCard({ label, value, color = "var(--accent)", borderColor }) {
  return (
    <div className="metric-card" style={{ borderTopColor: borderColor || color }}>
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color }}>{value ?? "—"}</div>
    </div>
  );
}

function BarChart({ data, labelKey, valueKey, color = "var(--accent)", format }) {
  const maxVal = Math.max(...data.map((d) => d[valueKey] || 0), 0.001);
  return (
    <div>
      {data.map((d, i) => {
        const raw = d[valueKey] || 0;
        const pct = Math.min((raw / maxVal) * 100, 100);
        const label = format ? format(raw) : `${(raw * 100).toFixed(1)}%`;
        return (
          <div key={i} style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ color: "var(--text-2)", fontSize: 12.5 }}>{d[labelKey]}</span>
              <span style={{ color: "var(--text-1)", fontSize: 12.5, fontWeight: 600 }}>{label}</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ background: color, width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CostGauge({ usedUsd, limitUsd, pct }) {
  const gaugeColor = pct >= 100 ? "#ef4444" : pct > 80 ? "#f97316" : pct > 60 ? "#f59e0b" : "#6366f1";
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ color: "var(--text-2)", fontSize: 13 }}>Cumulative Spend</span>
        <span style={{ color: gaugeColor, fontWeight: 800, fontSize: 18 }}>
          ${usedUsd?.toFixed(4)}
        </span>
      </div>

      {/* Gauge track */}
      <div style={{ position: "relative", marginBottom: 6 }}>
        <div className="progress-track" style={{ height: 14, borderRadius: 8 }}>
          <div className="progress-fill" style={{
            background: `linear-gradient(90deg, #6366f1, ${gaugeColor})`,
            width: `${Math.min(pct, 100)}%`,
            height: "100%", borderRadius: 8,
          }} />
        </div>
        {pct > 80 && pct < 100 && (
          <div style={{
            position: "absolute", top: -4, left: `${Math.min(pct, 98)}%`,
            width: 2, height: 22, background: "#f97316", borderRadius: 1,
          }} />
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>${usedUsd?.toFixed(4)} used</span>
        <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>
          ${limitUsd} limit · <span style={{ color: gaugeColor, fontWeight: 600 }}>{pct.toFixed(1)}%</span>
        </span>
      </div>

      {pct >= 80 && pct < 100 && (
        <div style={{
          marginTop: 8, padding: "6px 10px", borderRadius: 7, fontSize: 12,
          background: "rgba(249,115,22,0.1)", border: "1px solid rgba(249,115,22,0.3)",
          color: "#fdba74",
        }}>
          ⚠ Approaching cost limit — {(100 - pct).toFixed(1)}% remaining
        </div>
      )}
      {pct >= 100 && (
        <div style={{
          marginTop: 8, padding: "6px 10px", borderRadius: 7, fontSize: 12,
          background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
          color: "#fca5a5",
        }}>
          ✕ Cost limit exceeded — pipeline paused
        </div>
      )}
    </div>
  );
}

export default function ObservabilityDashboard() {
  const [health, setHealth]         = useState(null);
  const [metrics, setMetrics]       = useState(null);
  const [anomalies, setAnomalies]   = useState([]);
  const [tokenUsage, setTokenUsage] = useState(null);
  const [loading, setLoading]       = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [h, m, a, t] = await Promise.all([
        api.getPipelineHealth(), api.getMetrics(),
        api.getSystemAnomalies(), api.getTokenUsage(),
      ]);
      setHealth(h); setMetrics(m); setAnomalies(a); setTokenUsage(t);
      setLastRefresh(new Date());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); const iv = setInterval(refresh, 10000); return () => clearInterval(iv); }, [refresh]);

  if (loading) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "80px 0", color: "var(--text-3)" }}>
      <span className="spinner" />
      <span style={{ fontSize: 14 }}>Loading observability data…</span>
    </div>
  );

  const agentNames    = health ? Object.keys(health) : [];
  const flagRateData  = agentNames.map((a) => ({ agent: a.replace(/_/g, " "), val: health[a]["7d"]?.flag_rate || 0 }));
  const failRateData  = agentNames.map((a) => ({ agent: a.replace(/_/g, " "), val: health[a]["7d"]?.failure_rate || 0 }));
  const costLimit     = tokenUsage?.hard_limit_usd || 1.5;
  const costPct       = tokenUsage?.limit_utilization_pct || 0;

  return (
    <div className="fade-in">
      {/* ── Header ──────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: 23, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.4px" }}>
            Observability
          </h2>
          <div style={{ color: "var(--text-3)", fontSize: 12 }}>
            {lastRefresh ? `Last refreshed ${lastRefresh.toLocaleTimeString()}` : "Auto-refresh every 10s"}
          </div>
        </div>
        <button onClick={refresh} className="btn btn-ghost">↺ Refresh</button>
      </div>

      {/* ── Top metrics ─────────────────────────────────────── */}
      {metrics && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 20 }}>
          <MetricCard label="Total Invoices"  value={metrics.total_invoices}  color="var(--accent)"    borderColor="var(--accent)" />
          <MetricCard label="Approval Rate"   value={metrics.approval_rate != null ? `${(metrics.approval_rate * 100).toFixed(0)}%` : "—"}  color="#22c55e"  borderColor="#22c55e" />
          <MetricCard label="Flag Rate"       value={metrics.flag_rate != null ? `${(metrics.flag_rate * 100).toFixed(0)}%` : "—"}         color="#f97316"  borderColor="#f97316" />
          <MetricCard label="Rejection Rate"  value={metrics.rejection_rate != null ? `${(metrics.rejection_rate * 100).toFixed(0)}%` : "—"} color="#ef4444"  borderColor="#ef4444" />
          <MetricCard label="Rollback Rate"   value={metrics.rollback_rate != null ? `${(metrics.rollback_rate * 100).toFixed(1)}%` : "—"}   color="var(--text-2)" borderColor="var(--border-light)" />
        </div>
      )}

      {/* ── Agent health charts ─────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div className="card">
          <div className="section-title">Flag Rate by Agent (7 days)</div>
          {flagRateData.length > 0
            ? <BarChart data={flagRateData} labelKey="agent" valueKey="val" color="#f97316" />
            : <div style={{ color: "var(--text-3)", fontSize: 13 }}>No data yet.</div>}
        </div>

        <div className="card">
          <div className="section-title">Failure Rate by Agent (7 days)</div>
          {failRateData.length > 0
            ? <BarChart data={failRateData} labelKey="agent" valueKey="val" color="#ef4444" />
            : <div style={{ color: "var(--text-3)", fontSize: 13 }}>No data yet.</div>}
        </div>
      </div>

      {/* ── Vendor + Anomalies ──────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Vendor reliability */}
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "16px 20px 10px" }}>
            <div className="section-title" style={{ marginBottom: 0 }}>Vendor Reliability</div>
          </div>
          {metrics?.vendor_reliability_scores?.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  {["Vendor", "Invoices", "Flags", "Score"].map((h) => (
                    <th key={h} style={{ fontSize: 10.5 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...metrics.vendor_reliability_scores]
                  .sort((a, b) => b.reliability_score - a.reliability_score)
                  .map((v, i) => {
                    const sc = v.reliability_score;
                    const scoreColor = sc > 0.8 ? "#22c55e" : sc > 0.5 ? "#f97316" : "#ef4444";
                    return (
                      <tr key={i} style={{ cursor: "default" }}>
                        <td style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 500 }}>{v.vendor}</td>
                        <td style={{ fontSize: 13, color: "var(--text-2)" }}>{v.invoice_count}</td>
                        <td style={{ fontSize: 13, color: v.flag_count > 0 ? "#f97316" : "var(--text-3)" }}>{v.flag_count}</td>
                        <td>
                          <span style={{
                            background: `${scoreColor}15`,
                            color: scoreColor,
                            borderRadius: 20, padding: "2px 10px",
                            fontSize: 12, fontWeight: 700,
                          }}>
                            {(sc * 100).toFixed(0)}%
                          </span>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          ) : <div style={{ padding: "20px", color: "var(--text-3)", fontSize: 13 }}>No vendor data yet.</div>}
        </div>

        {/* System anomalies */}
        <div className="card">
          <div className="section-title">System Anomalies</div>
          {anomalies.length === 0 ? (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "12px 0", color: "#4ade80", fontSize: 13,
            }}>
              <span style={{
                width: 28, height: 28, borderRadius: "50%",
                background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, flexShrink: 0,
              }}>✓</span>
              No system anomalies detected
            </div>
          ) : anomalies.map((a, i) => {
            const ac = SEVERITY_COLOR[a.severity] || "var(--border-light)";
            return (
              <div key={i} style={{
                background: `${ac}0c`,
                border: `1px solid ${ac}30`,
                borderLeft: `3px solid ${ac}`,
                borderRadius: 8, padding: "10px 14px", marginBottom: 8,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 600 }}>{a.type?.replace(/_/g, " ")}</span>
                  <span style={{ color: ac, fontSize: 10.5, fontWeight: 700, textTransform: "uppercase" }}>{a.severity}</span>
                </div>
                <div style={{ color: "var(--text-2)", fontSize: 12 }}>{a.detail}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Token Usage ─────────────────────────────────────── */}
      {tokenUsage && (
        <div className="card">
          <div className="section-title">Token Usage & Cost Control</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
            {/* Cost gauge + per-agent */}
            <div>
              <CostGauge usedUsd={tokenUsage.cumulative_cost_usd} limitUsd={costLimit} pct={costPct} />

              <div style={{ marginTop: 20 }}>
                <div className="section-title">Cost by Agent</div>
                {tokenUsage.per_agent?.map((a, i) => (
                  <div key={i} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 0", borderBottom: "1px solid rgba(26,45,69,0.5)",
                  }}>
                    <div>
                      <div style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 500 }}>{a.agent_name}</div>
                      <div style={{ color: "var(--text-3)", fontSize: 11.5, marginTop: 1 }}>
                        {a.model} · {a.call_count} call{a.call_count !== 1 ? "s" : ""}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ color: "var(--text-1)", fontWeight: 700, fontSize: 13.5 }}>${a.total_cost_usd?.toFixed(4)}</div>
                      <div style={{ color: "var(--text-3)", fontSize: 11 }}>
                        {(a.total_prompt_tokens + a.total_completion_tokens).toLocaleString()} tokens
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Daily trend */}
            <div>
              <div className="section-title">Daily Cost Trend</div>
              {tokenUsage.daily_cost_trend?.length > 0 ? (
                <div>
                  {[...tokenUsage.daily_cost_trend].reverse().map((d, i) => {
                    const maxDailyRaw = Math.max(...tokenUsage.daily_cost_trend.map((x) => Number(x.daily_cost)), 0.001);
                    const pct = Math.min((Number(d.daily_cost) / maxDailyRaw) * 100, 100);
                    return (
                      <div key={i} style={{ marginBottom: 8 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                          <span style={{ color: "var(--text-2)", fontSize: 12 }}>{d.date}</span>
                          <span style={{ color: "var(--text-1)", fontSize: 12, fontWeight: 600 }}>${Number(d.daily_cost).toFixed(4)}</span>
                        </div>
                        <div className="progress-track" style={{ height: 6 }}>
                          <div className="progress-fill" style={{ background: "var(--accent)", width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ color: "var(--text-3)", fontSize: 13 }}>No cost data yet.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
