const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY;

// Only attached when VITE_API_KEY is set — matches the backend's
// BOMCOC_API_KEY (unset on both sides = no-op locally, see app/auth.py).
function authHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

export interface BOMItem {
  item_id: string;
  part_id: string | null;
  description: string | null;
  manufacturer: string | null;
  model: string | null;
  quantity: number | null;
  po_number: string | null;
}

export interface BOM {
  bom_id: string;
  project_id: string;
  filename: string;
  uploaded_at: string;
  version: number;
  status: string;
  items: BOMItem[];
}

export interface Validation {
  parameter: string;
  expected_value: string | null;
  actual_value: string | null;
  status: "PASS" | "FAIL" | "WARNING";
  reason: string | null;
}

export interface COC {
  coc_id: string;
  bom_id: string;
  filename: string;
  uploaded_at: string;
  document_type: string;
  status: string;
  validations: Validation[];
}

export interface ReportRow {
  parameter: string;
  expected: string | null;
  actual: string | null;
  status: "PASS" | "FAIL" | "WARNING";
  reason: string | null;
}

export interface Report {
  coc_id: string;
  filename: string;
  overall_status: "PASS" | "FAIL" | "WARNING";
  rows: ReportRow[];
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export async function listBOMs(): Promise<BOM[]> {
  const res = await fetch(`${API_BASE}/api/boms`, { headers: authHeaders() });
  return handle<BOM[]>(res);
}

export async function listCOCs(bomId: string): Promise<COC[]> {
  const res = await fetch(`${API_BASE}/api/boms/${bomId}/cocs`, { headers: authHeaders() });
  return handle<COC[]>(res);
}

export async function uploadBOM(projectId: string, file: File): Promise<BOM> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/boms`, { method: "POST", headers: authHeaders(), body: form });
  return handle<BOM>(res);
}

export async function uploadCOCs(bomId: string, files: File[]): Promise<COC[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${API_BASE}/api/boms/${bomId}/cocs`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handle<COC[]>(res);
}

export async function getReport(cocId: string): Promise<Report> {
  const res = await fetch(`${API_BASE}/api/cocs/${cocId}/report`, { headers: authHeaders() });
  return handle<Report>(res);
}

// A plain <a href> can't attach a custom header, so when an API key is
// configured the highlighted PDF is fetched here (with the header) and
// handed back as a same-origin blob: URL for the link to point at instead.
export async function highlightedPdfUrl(cocId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/cocs/${cocId}/highlighted-pdf`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error(`${res.status}: ${await res.text()}`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
