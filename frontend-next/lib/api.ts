// Same-origin calls to this app's proxy (app/api/v1/[...path]/route.ts),
// which adds the API key on the server. No key ever reaches the browser.
const BASE = "/api/v1";

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
  const res = await fetch(`${BASE}/upload`, {
    method: "POST",
    body: form,
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
  const res = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

/** Fetch the PDF and save it under the name the API gives it. */
export async function downloadReport(estimateId: number): Promise<void> {
  const res = await fetch(`${BASE}/report/${estimateId}`);
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

/** Estimates created in this browser, newest first (the proxy tracks them). */
export async function listMine(): Promise<AssessmentReport[]> {
  const res = await fetch(`${BASE}/mine`);
  if (!res.ok) throw new Error("Couldn't load your reports");
  return res.json();
}
