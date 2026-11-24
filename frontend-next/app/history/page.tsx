"use client";

import { useEffect, useState } from "react";
import { downloadReport, listMine, type AssessmentReport } from "@/lib/api";
import Link from "next/link";

export default function HistoryPage() {
  const [estimates, setEstimates] = useState<AssessmentReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listMine()
      .then(setEstimates)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Your reports</h2>
        <Link href="/" className="text-sm text-brand hover:underline">+ New assessment</Link>
      </div>

      {loading && <p className="text-gray-400">Loading…</p>}
      {error && <p className="text-red-500 text-sm">{error}</p>}

      {!loading && !error && estimates.length === 0 && (
        <p className="text-gray-400">No reports from this browser yet.</p>
      )}

      {estimates.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-brand text-white">
              <tr>
                {["#", "Vehicle", "Total", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {estimates.map((e, i) => (
                <tr key={e.estimate_id} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  <td className="px-4 py-3 text-gray-400">{e.estimate_id}</td>
                  <td className="px-4 py-3 font-medium">{e.vehicle.year} {e.vehicle.make} {e.vehicle.model}</td>
                  <td className="px-4 py-3 font-semibold">
                    ${Number(e.totals.grand_total).toLocaleString("en-US", { minimumFractionDigits: 0 })}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => e.estimate_id !== null && downloadReport(e.estimate_id).catch((err: Error) => console.error(err))}
                      className="text-brand hover:underline text-xs"
                    >
                      PDF
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
