const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// NOTE: a key shipped in browser code is visible to anyone who opens the site.
// It only deters casual abuse of the API; a public deployment should route
// calls through a server-side proxy that adds the key instead.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function withKey(headers: Record<string, string> = {}): Record<string, string> {
  return API_KEY ? { ...headers, "X-API-Key": API_KEY } : headers;
}

export interface UploadResponse {
  upload_id: string;
  image_count: number;
  quality_warnings: Array<{ image_filename: string; warning_type: string; message: string }>;
}

export interface DamageItem {
  component: string;
  damage_type: string;
  severity: number;
  description: string;
  recommendation: "repair" | "replace";
}

export interface CostEstimate {
  component: string;
  recommendation: string;
  // null when pricing_method is "unpriced"
  part_cost_low: string | null;
  part_cost_avg: string | null;
  part_cost_high: string | null;
  pricing_method: string;
  labor_hours: string;
  labor_cost: string;
  total_avg: string | null;
}

export interface AssessmentIssue {
  stage: "damage_detection" | "pricing" | "sanity_check";
  scope: string | null;
  detail: string;
}

export interface AssessmentReport {
  status: "complete" | "partial";
  issues: AssessmentIssue[];
  estimate_id: number | null;
  vehicle: { make: string; model: string; year: number; trim?: string; confidence: number; vin?: string };
  damage_assessment: {
    damages: DamageItem[];
    image_quality_warnings: Array<{ message: string }>;
    angle_guidance?: { suggestion: string };
    assessment_method: string;
  };
  cost_estimates: CostEstimate[];
  totals: { parts_total: string; labor_total: string; grand_total: string; unpriced_components: string[] };
  assessment_warnings: string[];
  disclaimer: string;
}

export async function uploadImages(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("images", f));
  const res = await fetch(`${BASE}/api/v1/upload`, {
    method: "POST",
    body: form,
    headers: withKey(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function analyzeUpload(
  uploadId: string,
  opts?: { make?: string; model?: string; year?: number; vin?: string; useConsensus?: boolean }
): Promise<AssessmentReport> {
  const res = await fetch(`${BASE}/api/v1/analyze`, {
    method: "POST",
    headers: withKey({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      upload_id: uploadId,
      make: opts?.make ?? null,
      model: opts?.model ?? null,
      year: opts?.year ?? null,
      vin: opts?.vin ?? null,
      use_consensus: opts?.useConsensus ?? false,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Analysis failed");
  }
  return res.json();
}

/** Fetch the PDF (with the API key) and save it; plain links can't send headers. */
export async function downloadReport(estimateId: number): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/report/${estimateId}`, { headers: withKey() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Report download failed");
  }
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `damage_report_${estimateId}.pdf`;
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function listEstimates() {
  const res = await fetch(`${BASE}/api/v1/estimates`, { headers: withKey() });
  if (!res.ok) throw new Error("Failed to load estimates");
  return res.json();
}
