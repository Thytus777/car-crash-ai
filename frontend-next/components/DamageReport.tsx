"use client";

import { useState } from "react";

import { downloadReport, type AssessmentReport } from "@/lib/api";

interface Props {
  report: AssessmentReport;
  onReset: () => void;
}

const money = (n: string | number | null) =>
  n === null ? "Unpriced" : `$${Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const label = (s: string) => s.replace(/_/g, " ");

function Severity({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="severity">
      <span className="severity__bar" aria-hidden="true">
        <i style={{ width: `${pct}%` }} />
      </span>
      {value.toFixed(2)}
    </span>
  );
}

export default function DamageReport({ report, onReset }: Props) {
  const { vehicle, damage_assessment, cost_estimates, totals, assessment_warnings, issues } = report;
  const [pdfError, setPdfError] = useState("");
  const id = report.estimate_id;

  return (
    <article>
      <div className="report-head">
        <div>
          <p className="report-no">{id !== null ? `Report No. ${id}` : "Report (not saved)"}</p>
          <h1 className="vehicle">
            {vehicle.year} {vehicle.make} {vehicle.model}
            {vehicle.trim ? ` ${vehicle.trim}` : ""}
          </h1>
          <p className="meta">
            Identified with {Math.round(vehicle.confidence * 100)}% confidence
            {vehicle.vin ? ` · VIN ${vehicle.vin}` : ""} · {label(damage_assessment.assessment_method)}
          </p>
        </div>
        <button type="button" className="button button--plain" onClick={onReset}>
          New report
        </button>
      </div>

      {report.status === "partial" && (
        <div className="note" role="status">
          <p className="note__title">Partial report: some steps couldn&apos;t finish</p>
          <ul>
            {issues.map((issue, i) => (
              <li key={i}>{issue.detail}</li>
            ))}
          </ul>
        </div>
      )}
      {damage_assessment.image_quality_warnings.length > 0 && (
        <div className="note">
          <p className="note__title">Photo quality</p>
          <ul>
            {damage_assessment.image_quality_warnings.map((w, i) => (
              <li key={i}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}
      {damage_assessment.angle_guidance?.suggestion && (
        <div className="note">
          <p className="note__title">For a better estimate</p>
          <p style={{ margin: 0 }}>{damage_assessment.angle_guidance.suggestion}</p>
        </div>
      )}
      {assessment_warnings.length > 0 && (
        <div className="note">
          <p className="note__title">Check these</p>
          <ul>
            {assessment_warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <section className="section" aria-labelledby="damage-label">
        <h2 className="section__label" id="damage-label">
          <span className="section__letter">A.</span> Damage
        </h2>
        {damage_assessment.damages.length === 0 ? (
          <p>No damage found in these photos.</p>
        ) : (
          <div className="scroll-x">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Part</th>
                  <th>Severity</th>
                  <th>Action</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {damage_assessment.damages.map((d, i) => (
                  <tr key={i}>
                    <td className="ledger__part">
                      {label(d.component)}
                      <span className="ledger__small">{d.damage_type}</span>
                    </td>
                    <td>
                      <Severity value={d.severity} />
                    </td>
                    <td>
                      <span className={d.recommendation === "replace" ? "action action--replace" : "action"}>
                        {d.recommendation}
                      </span>
                    </td>
                    <td>{d.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {cost_estimates.length > 0 && (
        <section className="section" aria-labelledby="cost-label">
          <h2 className="section__label" id="cost-label">
            <span className="section__letter">B.</span> Costs
          </h2>
          <div className="scroll-x">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Part</th>
                  <th className="num">Part price</th>
                  <th className="num">Labour</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {cost_estimates.map((c, i) => (
                  <tr key={i}>
                    <td className="ledger__part">
                      {label(c.component)}
                      <span className="ledger__small">{label(c.pricing_method)}</span>
                    </td>
                    <td className="num">
                      {c.part_cost_avg === null ? (
                        "Unpriced"
                      ) : (
                        <>
                          {money(c.part_cost_avg)}
                          <span className="ledger__small">
                            {money(c.part_cost_low)} to {money(c.part_cost_high)}
                          </span>
                        </>
                      )}
                    </td>
                    <td className="num">
                      {money(c.labor_cost)}
                      <span className="ledger__small">{c.labor_hours} h</span>
                    </td>
                    <td className="num">{money(c.total_avg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="totals">
        <dl>
          <dt>Parts</dt>
          <dd>{money(totals.parts_total)}</dd>
          <dt>Labour</dt>
          <dd>{money(totals.labor_total)}</dd>
          {totals.unpriced_components.length > 0 && (
            <>
              <dt>Unpriced</dt>
              <dd>{totals.unpriced_components.map(label).join(", ")}</dd>
            </>
          )}
        </dl>
        <div className="stamp" role="img" aria-label={`Estimated total ${money(totals.grand_total)}`}>
          <span className="stamp__label">Estimate</span>
          <span className="stamp__value">{money(totals.grand_total)}</span>
        </div>
      </div>

      {id !== null && (
        <div className="actions">
          <button
            type="button"
            className="button"
            onClick={() => {
              setPdfError("");
              downloadReport(id).catch((e: Error) => setPdfError(e.message));
            }}
          >
            Download PDF
          </button>
          {pdfError && <span role="alert">{pdfError}</span>}
        </div>
      )}

      <p className="disclaimer">{report.disclaimer}</p>
    </article>
  );
}
