import React, { useState } from "react";

const COLORS = {
  orchestrator: "#6366f1",
  extractor: "#f59e0b",
  formatter: "#f59e0b",
  service_check: "#3b82f6",
  anomaly_check: "#3b82f6",
  pattern_recognition: "#3b82f6",
  decision_agent: "#8b5cf6",
  notifier: "#06b6d4",
  database: "#334155",
  frontend: "#22c55e",
  observability: "#ec4899",
  human: "#f97316",
};

function AgentBox({ x, y, width, height, label, sublabel, color, onClick, isSelected }) {
  return (
    <g onClick={onClick} style={{ cursor: "pointer" }}>
      <rect x={x} y={y} width={width} height={height} rx={8}
        fill={isSelected ? color : `${color}22`}
        stroke={color} strokeWidth={isSelected ? 2.5 : 1.5}
        style={{ transition: "all 0.2s" }} />
      <text x={x + width / 2} y={y + height / 2 - (sublabel ? 7 : 0)} textAnchor="middle"
        fill={isSelected ? "#fff" : color} fontSize={13} fontWeight={600}
        style={{ userSelect: "none" }}>
        {label}
      </text>
      {sublabel && (
        <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle"
          fill={isSelected ? "#ffffffaa" : `${color}99`} fontSize={10}
          style={{ userSelect: "none" }}>
          {sublabel}
        </text>
      )}
    </g>
  );
}

function Arrow({ x1, y1, x2, y2, color = "#475569", label, dashed = false }) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;

  return (
    <g>
      <defs>
        <marker id={`arrow-${color.replace("#", "")}`} markerWidth={8} markerHeight={8}
          refX={6} refY={3} orient="auto">
          <path d="M0,0 L0,6 L8,3 z" fill={color} />
        </marker>
      </defs>
      <line x1={x1} y1={y1} x2={x2} y2={y2}
        stroke={color} strokeWidth={1.5}
        strokeDasharray={dashed ? "4,4" : undefined}
        markerEnd={`url(#arrow-${color.replace("#", "")})`} />
      {label && (
        <text x={mx} y={my - 5} textAnchor="middle" fill={color} fontSize={9}
          style={{ userSelect: "none" }}>
          {label}
        </text>
      )}
    </g>
  );
}

function DbTable({ x, y, name }) {
  return (
    <g>
      <rect x={x} y={y} width={110} height={22} rx={4}
        fill="#1e293b" stroke="#334155" strokeWidth={1} />
      <text x={x + 55} y={y + 15} textAnchor="middle" fill="#94a3b8" fontSize={10}
        style={{ userSelect: "none" }}>
        {name}
      </text>
    </g>
  );
}

const DETAILS = {
  orchestrator: {
    title: "Orchestrator",
    model: "No LLM (pure routing logic)",
    role: "Pipeline coordinator. Posts tasks to queue, manages parallel execution, applies tiered error handling, suggests memory writes.",
    memory: ["queue", "event_log", "invoices", "agent_instructions"],
  },
  extractor: {
    title: "Extractor Agent",
    model: "gpt-4o-mini",
    role: "Detects file type and extracts raw text. Supports PDF, images, DOCX, XML, JSON, EML.",
    memory: ["invoices"],
  },
  formatter: {
    title: "Formatter Agent",
    model: "gpt-4o-mini",
    role: "Structures raw text into standardized invoice JSON. Validates math consistency.",
    memory: ["invoices", "system_knowledge:anomaly_rules"],
  },
  service_check: {
    title: "Service Check Agent",
    model: "gpt-4o-mini",
    role: "Validates line items against approved services catalog. Flags unauthorized or over-threshold services.",
    memory: ["system_knowledge:approved_services", "system_knowledge:approved_vendors"],
  },
  anomaly_check: {
    title: "Anomaly Check Agent",
    model: "gpt-4o-mini",
    role: "Detects duplicates, unusual amounts, round number bias, missing fields, date anomalies.",
    memory: ["system_knowledge:anomaly_rules"],
  },
  pattern_recognition: {
    title: "Pattern Recognition Agent",
    model: "gpt-4o-mini",
    role: "Compares invoice against vendor history. Identifies price changes, new/removed items, trends.",
    memory: ["operational_memory:vendor_history", "operational_memory:invoice_patterns"],
  },
  decision_agent: {
    title: "Decision Agent",
    model: "gpt-4o (premium)",
    role: "Synthesizes all agent outputs with weighted scoring. Produces final verdict: approved/flagged/rejected/requires_human.",
    memory: ["event_log", "system_knowledge:decision_weights"],
  },
  notifier: {
    title: "Notifier Agent",
    model: "gpt-4o-mini",
    role: "Generates human-readable notifications for mid-pipeline flags (operational) and final verdicts (summary).",
    memory: ["event_log", "final_output"],
  },
};

export default function ArchitectureDiagram() {
  const [selected, setSelected] = useState(null);

  function handleSelect(key) {
    setSelected(selected === key ? null : key);
  }

  const detail = selected ? DETAILS[selected] : null;

  return (
    <div>
      <h2 style={{ margin: "0 0 8px", fontSize: 22, fontWeight: 700, color: "#f1f5f9" }}>Architecture Diagram</h2>
      <p style={{ color: "#64748b", fontSize: 13, marginBottom: 20 }}>Click any component to see its role and memory access. Parallel execution branch highlighted in blue.</p>

      <div style={{ display: "grid", gridTemplateColumns: detail ? "1fr 320px" : "1fr", gap: 16 }}>
        {/* SVG Diagram */}
        <div style={{ background: "#1e293b", borderRadius: 12, border: "1px solid #334155", overflow: "auto", padding: 8 }}>
          <svg width={900} height={700} style={{ display: "block" }}>
            <defs>
              <marker id="arrowgray" markerWidth={8} markerHeight={8} refX={6} refY={3} orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#475569" />
              </marker>
              <marker id="arrowblue" markerWidth={8} markerHeight={8} refX={6} refY={3} orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#3b82f6" />
              </marker>
              <marker id="arrowpink" markerWidth={8} markerHeight={8} refX={6} refY={3} orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#ec4899" />
              </marker>
              <marker id="arrowgreen" markerWidth={8} markerHeight={8} refX={6} refY={3} orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#22c55e" />
              </marker>
              <marker id="arroworange" markerWidth={8} markerHeight={8} refX={6} refY={3} orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#f97316" />
              </marker>
            </defs>

            {/* REST API Layer label */}
            <rect x={20} y={20} width={860} height={60} rx={8} fill="#0f172a" stroke="#334155" strokeDasharray="4,3" strokeWidth={1} />
            <text x={450} y={45} textAnchor="middle" fill="#475569" fontSize={11}>REST API Layer</text>
            {/* Frontend */}
            <AgentBox x={60} y={30} width={120} height={40} label="React Frontend" sublabel="5 views" color={COLORS.frontend}
              onClick={() => {}} isSelected={false} />
            {/* API endpoints */}
            {["/api/invoices", "/api/memory", "/api/observability", "/api/notifications"].map((ep, i) => (
              <g key={ep}>
                <rect x={220 + i * 155} y={32} width={140} height={36} rx={6} fill="#1e293b" stroke="#334155" strokeWidth={1} />
                <text x={220 + i * 155 + 70} y={54} textAnchor="middle" fill="#64748b" fontSize={10}>{ep}</text>
              </g>
            ))}

            {/* Orchestrator */}
            <AgentBox x={360} y={110} width={180} height={52} label="Orchestrator" sublabel="No LLM · Pure routing" color={COLORS.orchestrator}
              onClick={() => handleSelect("orchestrator")} isSelected={selected === "orchestrator"} />

            {/* Arrow: API → Orchestrator */}
            <line x1={450} y1={80} x2={450} y2={110} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />
            <text x={465} y={98} fill="#475569" fontSize={9}>upload</text>

            {/* Extractor */}
            <AgentBox x={200} y={210} width={140} height={48} label="Extractor" sublabel="gpt-4o-mini" color={COLORS.extractor}
              onClick={() => handleSelect("extractor")} isSelected={selected === "extractor"} />
            <line x1={410} y1={162} x2={290} y2={210} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />

            {/* Formatter */}
            <AgentBox x={390} y={210} width={140} height={48} label="Formatter" sublabel="gpt-4o-mini" color={COLORS.formatter}
              onClick={() => handleSelect("formatter")} isSelected={selected === "formatter"} />
            <line x1={340} y1={234} x2={390} y2={234} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />

            {/* Parallel bracket */}
            <rect x={145} y={300} width={570} height={110} rx={8} fill="#3b82f622" stroke="#3b82f6" strokeWidth={1.5} strokeDasharray="5,3" />
            <text x={430} y={318} textAnchor="middle" fill="#3b82f6" fontSize={11} fontWeight={600}>Parallel Execution</text>

            {/* Parallel agents */}
            <AgentBox x={160} y={324} width={150} height={48} label="Service Check" sublabel="gpt-4o-mini" color={COLORS.service_check}
              onClick={() => handleSelect("service_check")} isSelected={selected === "service_check"} />
            <AgentBox x={355} y={324} width={155} height={48} label="Anomaly Check" sublabel="gpt-4o-mini" color={COLORS.anomaly_check}
              onClick={() => handleSelect("anomaly_check")} isSelected={selected === "anomaly_check"} />
            <AgentBox x={555} y={324} width={150} height={48} label="Pattern Recog." sublabel="gpt-4o-mini" color={COLORS.pattern_recognition}
              onClick={() => handleSelect("pattern_recognition")} isSelected={selected === "pattern_recognition"} />

            {/* Formatter → Parallel */}
            <line x1={460} y1={258} x2={460} y2={300} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />

            {/* Decision Agent */}
            <AgentBox x={355} y={460} width={195} height={52} label="Decision Agent" sublabel="gpt-4o (premium)" color={COLORS.decision_agent}
              onClick={() => handleSelect("decision_agent")} isSelected={selected === "decision_agent"} />
            <line x1={430} y1={410} x2={430} y2={460} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />

            {/* Notifier */}
            <AgentBox x={355} y={558} width={195} height={48} label="Notifier" sublabel="gpt-4o-mini" color={COLORS.notifier}
              onClick={() => handleSelect("notifier")} isSelected={selected === "notifier"} />
            <line x1={452} y1={512} x2={452} y2={558} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />

            {/* Human in the loop */}
            <rect x={620} y={456} width={130} height={54} rx={8} fill="#f9731622" stroke="#f97316" strokeWidth={1.5} />
            <text x={685} y={480} textAnchor="middle" fill="#f97316" fontSize={12} fontWeight={600}>Human Review</text>
            <text x={685} y={496} textAnchor="middle" fill="#f9731699" fontSize={10}>Approve / Reject</text>
            <text x={685} y={508} textAnchor="middle" fill="#f9731699" fontSize={10}>Rollback / Rerun</text>
            <line x1={550} y1={486} x2={620} y2={486} stroke="#f97316" strokeWidth={1.5} strokeDasharray="4,3" markerEnd="url(#arroworange)" />
            <text x={585} y={480} textAnchor="middle" fill="#f97316" fontSize={9}>awaiting human</text>

            {/* Database */}
            <rect x={730} y={110} width={145} height={420} rx={10} fill="#0f172a" stroke="#334155" strokeWidth={1.5} />
            <text x={802} y={133} textAnchor="middle" fill="#64748b" fontSize={11} fontWeight={600}>SQLite Database</text>
            {["invoices","queue","event_log","agent_instructions","system_knowledge","operational_memory","user_actions","final_output","notifications","token_usage"].map((t, i) => (
              <DbTable key={t} x={740} y={142 + i * 36} name={t} />
            ))}
            {/* DB connections */}
            <line x1={730} y1={300} x2={700} y2={348} stroke="#334155" strokeWidth={1} markerEnd="url(#arrowgray)" strokeDasharray="3,2" />

            {/* Observability Monitor */}
            <rect x={20} y={400} width={120} height={90} rx={8} fill="#ec489922" stroke="#ec4899" strokeWidth={1.5} />
            <text x={80} y={425} textAnchor="middle" fill="#ec4899" fontSize={11} fontWeight={600}>Observability</text>
            <text x={80} y={441} textAnchor="middle" fill="#ec489999" fontSize={10}>Monitor</text>
            <text x={80} y={457} textAnchor="middle" fill="#ec489999" fontSize={10}>background</text>
            <text x={80} y={473} textAnchor="middle" fill="#ec489999" fontSize={10}>thread</text>
            <text x={80} y={485} textAnchor="middle" fill="#ec489999" fontSize={10}>60s polling</text>
            <line x1={140} y1={445} x2={730} y2={260} stroke="#ec4899" strokeWidth={1} strokeDasharray="3,3" markerEnd="url(#arrowpink)" />

            {/* Memory stores labels */}
            <text x={20} y={545} fill="#64748b" fontSize={10}>Memory Stores:</text>
            <rect x={20} y={550} width={95} height={20} rx={4} fill="#6366f122" stroke="#6366f1" strokeWidth={1} />
            <text x={67} y={564} textAnchor="middle" fill="#6366f1" fontSize={9}>system_knowledge</text>
            <rect x={125} y={550} width={95} height={20} rx={4} fill="#8b5cf622" stroke="#8b5cf6" strokeWidth={1} />
            <text x={172} y={564} textAnchor="middle" fill="#8b5cf6" fontSize={9}>operational_memory</text>
            <text x={220} y={595} fill="#64748b" fontSize={9}>Human approval</text>
            <text x={220} y={607} fill="#64748b" fontSize={9}>required for writes</text>

            {/* Legend */}
            <text x={20} y={640} fill="#475569" fontSize={10}>Legend:</text>
            <line x1={70} y1={636} x2={100} y2={636} stroke="#475569" strokeWidth={1.5} markerEnd="url(#arrowgray)" />
            <text x={108} y={640} fill="#475569" fontSize={9}>Sequential flow</text>
            <line x1={200} y1={636} x2={230} y2={636} stroke="#3b82f6" strokeWidth={1.5} strokeDasharray="4,3" />
            <text x={238} y={640} fill="#3b82f6" fontSize={9}>Parallel execution</text>
            <line x1={340} y1={636} x2={370} y2={636} stroke="#f97316" strokeWidth={1.5} strokeDasharray="4,3" />
            <text x={378} y={640} fill="#f97316" fontSize={9}>Human-in-the-loop</text>
            <line x1={480} y1={636} x2={510} y2={636} stroke="#ec4899" strokeWidth={1.5} strokeDasharray="3,3" />
            <text x={518} y={640} fill="#ec4899" fontSize={9}>Observability (read-only)</text>
          </svg>
        </div>

        {/* Detail panel */}
        {detail && (
          <div style={{ background: "#1e293b", borderRadius: 12, border: "1px solid #334155", padding: 20, alignSelf: "start" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <h3 style={{ margin: 0, color: "#f1f5f9", fontSize: 16 }}>{detail.title}</h3>
              <button onClick={() => setSelected(null)}
                style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 18 }}>×</button>
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ color: "#64748b", fontSize: 11, textTransform: "uppercase", marginBottom: 4 }}>Model</div>
              <div style={{ color: detail.model.includes("premium") ? "#8b5cf6" : "#e2e8f0", fontWeight: 600, fontSize: 13 }}>{detail.model}</div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ color: "#64748b", fontSize: 11, textTransform: "uppercase", marginBottom: 4 }}>Role</div>
              <div style={{ color: "#94a3b8", fontSize: 13, lineHeight: 1.6 }}>{detail.role}</div>
            </div>
            <div>
              <div style={{ color: "#64748b", fontSize: 11, textTransform: "uppercase", marginBottom: 6 }}>Memory Access</div>
              {detail.memory.map((m, i) => (
                <div key={i} style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "4px 10px", fontSize: 11, color: "#94a3b8", marginBottom: 4 }}>
                  {m}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
