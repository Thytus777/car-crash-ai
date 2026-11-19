"use client";

import clsx from "clsx";
import type { AssessmentReport } from "@/lib/api";

interface Props {
  report: AssessmentReport;
  estimateId?: number;
  onReset: () => void;
}

function SeverityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.6 ? "bg-red-500" : value >= 0.3 ? "bg-yellow-400" : "bg-green-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500">{pct}%</span>
    </div>
  );
}

function Badge({ value }: { value: string }) {
  return (
    <span className={clsx(
      "inline-block px-2 py-0.5 rounded-full text-xs font-semibold",
      value === "replace" ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
    )}>
      {value.toUpperCase()}
    </span>
  );
}

export default function DamageReport({ report, estimateId, onReset }: Props) {
  const { vehicle, damage_assessment, cost_estimates, totals, assessment_warnings } = report;
  const fmt = (n: string | number) => `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-brand">
            {vehicle.year} {vehicle.make} {vehicle.model}{vehicle.trim ? ` ${vehicle.trim}` : ""}
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            AI confidence: {Math.round(vehicle.confidence * 100)}%
            {vehicle.vin && <> · VIN: {vehicle.vin}</>}
            {" · "}Method: {damage_assessment.assessment_method.replace("_", " ")}
          </p>
        </div>
        <button onClick={onReset} className="text-sm text-brand hover:underline">
          ← New assessment
        </button>
      </div>

      {/* Quality warnings */}
      {damage_assessment.image_quality_warnings.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="font-semibold text-red-700 mb-1">Image Quality Issues</p>
          {damage_assessment.image_quality_warnings.map((w, i) => (
            <p key={i} className="text-sm text-red-600">• {w.message}</p>
          ))}
        </div>
      )}

      {/* Angle guidance */}
      {damage_assessment.angle_guidance?.angles_missing.length ? (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700">
          📷 {damage_assessment.angle_guidance.suggestion}
        </div>
      ) : null}

      {/* Assessment warnings (sanity check) */}
      {assessment_warnings.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="font-semibold text-yellow-800 mb-1">⚠ Assessment Flags</p>
          {assessment_warnings.map((w, i) => (
            <p key={i} className="text-sm text-yellow-700">• {w}</p>
          ))}
        </div>
      )}

      {/* Damage table */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Damage Assessment</h3>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-brand text-white">
              <tr>
                {["Component", "Damage", "Severity", "Action", "Description"].map((h) => (
                  <th key={h} className="px-4 py-2 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {damage_assessment.damages.map((d, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  <td className="px-4 py-2 font-medium capitalize">{d.component.replace(/_/g, " ")}</td>
                  <td className="px-4 py-2 capitalize">{d.damage_type}</td>
                  <td className="px-4 py-2"><SeverityBar value={d.severity} /></td>
                  <td className="px-4 py-2"><Badge value={d.recommendation} /></td>
                  <td className="px-4 py-2 text-gray-600 max-w-xs">{d.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cost table */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Cost Breakdown</h3>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-brand text-white">
              <tr>
                {["Component", "Parts (Low–High)", "Labor", "Total"].map((h) => (
                  <th key={h} className="px-4 py-2 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cost_estimates.map((c, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  <td className="px-4 py-2 font-medium capitalize">
                    {c.component.replace(/_/g, " ")}
                    <span className="block text-xs text-gray-400">{c.pricing_method.replace(/_/g, " ")}</span>
                  </td>
                  <td className="px-4 py-2">
                    {fmt(c.part_cost_low)} – {fmt(c.part_cost_high)}
                    <span className="block text-xs text-gray-400">avg {fmt(c.part_cost_avg)}</span>
                  </td>
                  <td className="px-4 py-2">{fmt(c.labor_cost)}</td>
                  <td className="px-4 py-2 font-semibold">{fmt(c.total_avg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Totals */}
      <div className="bg-brand text-white rounded-xl p-6 flex gap-8">
        {[
          ["Parts Total", totals.parts_total],
          ["Labor Total", totals.labor_total],
          ["Grand Total", totals.grand_total],
        ].map(([label, value]) => (
          <div key={label}>
            <p className="text-xs opacity-75 uppercase tracking-wide">{label}</p>
            <p className="text-3xl font-bold mt-0.5">{fmt(value)}</p>
          </div>
        ))}
        {estimateId && (
          <div className="ml-auto self-center">
            <a
              href={`/api/v1/report/${estimateId}`}
              target="_blank"
              rel="noreferrer"
              className="bg-white text-brand font-semibold px-4 py-2 rounded-lg text-sm hover:bg-blue-50 transition-colors"
            >
              Download PDF
            </a>
          </div>
        )}
      </div>

      {/* Disclaimer */}
      <p className="text-xs text-gray-400">{report.disclaimer}</p>
    </div>
  );
}
