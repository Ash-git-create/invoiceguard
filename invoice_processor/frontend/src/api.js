const BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Invoices
  listInvoices: () => apiFetch("/api/invoices"),
  getInvoice: (id) => apiFetch(`/api/invoices/${id}`),
  uploadInvoice: (file) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE_URL}/api/invoices/upload`, { method: "POST", body: form }).then((r) => r.json());
  },
  approveFlag: (id, data) => apiFetch(`/api/invoices/${id}/approve-flag`, { method: "POST", body: JSON.stringify(data) }),
  rejectFlag: (id, data) => apiFetch(`/api/invoices/${id}/reject-flag`, { method: "POST", body: JSON.stringify(data) }),
  rollback: (id, data) => apiFetch(`/api/invoices/${id}/rollback`, { method: "POST", body: JSON.stringify(data) }),
  rerun: (id, data) => apiFetch(`/api/invoices/${id}/rerun`, { method: "POST", body: JSON.stringify(data) }),

  // Memory
  getPendingMemory: () => apiFetch("/api/memory/pending"),
  approveMemory: (id, data) => apiFetch(`/api/memory/approve/${id}`, { method: "POST", body: JSON.stringify(data) }),
  rejectMemory: (id, data) => apiFetch(`/api/memory/reject/${id}`, { method: "POST", body: JSON.stringify(data) }),
  getApprovedMemory: (category) => apiFetch(`/api/memory/approved${category ? `?category=${category}` : ""}`),
  getSystemKnowledge: (category) => apiFetch(`/api/memory/system-knowledge${category ? `?category=${category}` : ""}`),
  getAgentInstructions: () => apiFetch("/api/agent-instructions"),

  // Observability
  getPipelineHealth: () => apiFetch("/api/observability/pipeline-health"),
  getInvoiceTrace: (id) => apiFetch(`/api/observability/invoice/${id}/trace`),
  getSystemAnomalies: () => apiFetch("/api/observability/anomalies"),
  getMetrics: () => apiFetch("/api/observability/metrics"),
  getTokenUsage: () => apiFetch("/api/observability/token-usage"),

  // Notifications
  getPendingNotifications: () => apiFetch("/api/notifications/pending"),
  getAllNotifications: (invoiceId) => apiFetch(`/api/notifications${invoiceId ? `?invoice_id=${invoiceId}` : ""}`),
  acknowledgeNotification: (id) => apiFetch(`/api/notifications/${id}/acknowledge`, { method: "POST" }),
  acknowledgeAll: () => apiFetch("/api/notifications/acknowledge-all", { method: "POST" }),
};
