"use client";

import { useState } from "react";
import UploadZone from "@/components/UploadZone";
import DamageReport from "@/components/DamageReport";
import { uploadImages, analyzeUpload, type AssessmentReport } from "@/lib/api";

type Stage = "upload" | "options" | "analyzing" | "result" | "error";

export default function HomePage() {
  const [stage, setStage] = useState<Stage>("upload");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadId, setUploadId] = useState("");
  const [qualityWarnings, setQualityWarnings] = useState<string[]>([]);
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [error, setError] = useState("");

  // Options
  const [vin, setVin] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [useConsensus, setUseConsensus] = useState(false);

  async function handleFiles(selected: File[]) {
    setFiles(selected);
    setStage("options");
  }

  async function handleAnalyze() {
    setStage("analyzing");
    setError("");
    try {
      const up = await uploadImages(files);
      setUploadId(up.upload_id);
      setQualityWarnings(up.quality_warnings.map((w) => w.message));

      const result = await analyzeUpload(up.upload_id, {
        vin: vin || undefined,
        make: make || undefined,
        model: model || undefined,
        year: year ? Number(year) : undefined,
        useConsensus,
      });

      // vehicle_confirmation_needed response
      if ("status" in result && (result as { status: string }).status === "vehicle_confirmation_needed") {
        // In a full implementation this would open a confirmation modal.
        // For now, surface it as an error with guidance.
        setError(
          "Low confidence on vehicle ID. Please fill in Make, Model, Year and try again."
        );
        setStage("error");
        return;
      }

      setReport(result as AssessmentReport);
      setStage("result");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setStage("error");
    }
  }

  function reset() {
    setStage("upload");
    setFiles([]);
    setUploadId("");
    setQualityWarnings([]);
    setReport(null);
    setError("");
    setVin(""); setMake(""); setModel(""); setYear("");
    setUseConsensus(false);
  }

  return (
    <div className="space-y-6">
      {(stage === "upload" || stage === "options") && (
        <div>
          <h2 className="text-xl font-bold mb-1">New Assessment</h2>
          <p className="text-sm text-gray-500 mb-6">
            Upload crash photos — we'll identify the vehicle, detect damage, and estimate repair costs.
          </p>

          <UploadZone onFiles={handleFiles} disabled={stage === "options"} />

          {files.length > 0 && (
            <p className="text-sm text-gray-500 mt-2">{files.length} photo(s) selected</p>
          )}

          {stage === "options" && (
            <div className="mt-6 bg-white border border-gray-200 rounded-xl p-5 space-y-4">
              <h3 className="font-semibold">Options <span className="font-normal text-gray-400 text-sm">(all optional)</span></h3>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">VIN (recommended for accuracy)</label>
                <input
                  value={vin}
                  onChange={(e) => setVin(e.target.value.toUpperCase())}
                  maxLength={17}
                  placeholder="1HGCM8263A000001"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Make", value: make, set: setMake, placeholder: "Toyota" },
                  { label: "Model", value: model, set: setModel, placeholder: "Camry" },
                  { label: "Year", value: year, set: setYear, placeholder: "2020" },
                ].map(({ label, value, set, placeholder }) => (
                  <div key={label}>
                    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                    <input
                      value={value}
                      onChange={(e) => set(e.target.value)}
                      placeholder={placeholder}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
                    />
                  </div>
                ))}
              </div>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useConsensus}
                  onChange={(e) => setUseConsensus(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm text-gray-700">
                  High-confidence mode (runs both AI providers — ~2× slower, higher cost)
                </span>
              </label>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleAnalyze}
                  className="bg-brand text-white font-semibold px-6 py-2.5 rounded-lg hover:bg-brand-dark transition-colors"
                >
                  Analyze Damage
                </button>
                <button onClick={reset} className="text-sm text-gray-500 hover:text-gray-700">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {stage === "analyzing" && (
        <div className="flex flex-col items-center justify-center py-24 space-y-4">
          <div className="w-12 h-12 border-4 border-brand border-t-transparent rounded-full animate-spin" />
          <p className="text-lg font-semibold text-gray-700">Analyzing damage…</p>
          <p className="text-sm text-gray-400">This usually takes 15–30 seconds</p>
        </div>
      )}

      {stage === "error" && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 space-y-3">
          <p className="font-semibold text-red-700">Analysis failed</p>
          <p className="text-sm text-red-600">{error}</p>
          <button onClick={() => setStage("options")} className="text-sm text-brand hover:underline">
            ← Try again
          </button>
        </div>
      )}

      {stage === "result" && report && (
        <DamageReport report={report} onReset={reset} />
      )}
    </div>
  );
}
