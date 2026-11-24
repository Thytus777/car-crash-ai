"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { downloadReport, listMine, type AssessmentReport } from "@/lib/api";

const money = (n: string) => `$${Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

export default function HistoryPage() {
  const [reports, setReports] = useState<AssessmentReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listMine()
      .then(setReports)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="form-title">Your reports</h1>
      <p className="lede">Reports made in this browser. Other people&apos;s reports are never shown here.</p>

      {loading && <p role="status">Loading your reports…</p>}
      {error && (
        <div className="note note--alarm" role="alert">
          <p className="note__title">Couldn&apos;t load your reports</p>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}
      {!loading && !error && reports.length === 0 && (
        <p className="empty">
          No reports yet. <Link href="/">Make your first one</Link>.
        </p>
      )}

      {reports.length > 0 && (
        <ul className="copies">
          {reports.map((r) => (
            <li className="copy" key={r.estimate_id}>
              <span className="copy__no">Report No. {r.estimate_id}</span>
              <h2 className="copy__vehicle">
                {r.vehicle.year} {r.vehicle.make} {r.vehicle.model}
              </h2>
              <span>
                {r.damage_assessment.damages.length} damaged part
                {r.damage_assessment.damages.length === 1 ? "" : "s"}
              </span>
              <span className="copy__total">{money(r.totals.grand_total)}</span>
              {r.estimate_id !== null && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => downloadReport(r.estimate_id as number).catch((e: Error) => setError(e.message))}
                >
                  Download PDF
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
