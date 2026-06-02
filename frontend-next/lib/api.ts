const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  part_cost_low: string;
  part_cost_avg: string;
  part_cost_high: string;
  pricing_method: string;
  labor_hours: string;
  labor_cost: string;
  total_avg: string;
}

export interface AssessmentReport {
  vehicle: { make: string; model: string; year: number; trim?: string; confidence: number; vin?: string };
  damage_assessment: {
    damages: DamageItem[];
    image_quality_warnings: Array<{ message: string }>;
    angle_guidance?: { angles_missing: string[]; suggestion: string };
    assessment_method: string;
  };
  cost_estimates: CostEstimate[];
  totals: { parts_total: string; labor_total: string; grand_total: string };
  assessment_warnings: string[];
  disclaimer: string;
}

export async function uploadImages(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("images", f));
  const res = await fetch(`${BASE}/api/v1/upload`, { method: "POST", body: form });
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

export function reportPdfUrl(estimateId: number): string {
  return `${BASE}/api/v1/report/${estimateId}`;
}

export async function listEstimates() {
  const res = await fetch(`${BASE}/api/v1/estimates`);
  if (!res.ok) throw new Error("Failed to load estimates");
  return res.json();
}
