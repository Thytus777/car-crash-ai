"use client";

import { useEffect, useState } from "react";
import { listEstimates } from "@/lib/api";
import Link from "next/link";

interface EstimateSummary {
  id: number;
  upload_id: string;
  created_at: string;
  vehicle: string;
  grand_total: number;
}

export default function HistoryPage() {
  const [estimates, setEstimates] = useState<EstimateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listEstimates()
      .then(setEstimates)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Estimate History</h2>
        <Link href="/" className="text-sm text-brand hover:underline">+ New assessment</Link>
      </div>

      {loading && <p className="text-gray-400">Loading…</p>}
      {error && <p className="text-red-500 text-sm">{error}</p>}

      {!loading && !error && estimates.length === 0 && (
        <p className="text-gray-400">No estimates yet.</p>
      )}

      {estimates.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-brand text-white">
              <tr>
                {["#", "Date", "Vehicle", "Total", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {estimates.map((e, i) => (
                <tr key={e.id} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  <td className="px-4 py-3 text-gray-400">{e.id}</td>
                  <td className="px-4 py-3">{new Date(e.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 font-medium">{e.vehicle}</td>
                  <td className="px-4 py-3 font-semibold">
                    ${Number(e.grand_total).toLocaleString("en-US", { minimumFractionDigits: 0 })}
                  </td>
                  <td className="px-4 py-3">
                    <a
                      href={`/api/v1/report/${e.id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-brand hover:underline text-xs"
                    >
                      PDF
                    </a>
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
