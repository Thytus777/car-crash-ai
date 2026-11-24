"use client";

import { useState } from "react";

import DamageReport from "@/components/DamageReport";
import UploadZone from "@/components/UploadZone";
import { analyzeUpload, uploadImages, type AssessmentReport } from "@/lib/api";

type Stage = "form" | "analyzing" | "result";

export default function HomePage() {
  const [stage, setStage] = useState<Stage>("form");
  const [files, setFiles] = useState<File[]>([]);
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [error, setError] = useState("");
  const [needsVehicle, setNeedsVehicle] = useState(false);

  const [vin, setVin] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [useConsensus, setUseConsensus] = useState(false);

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length) {
      setError("Add at least one photo of the car first.");
      return;
    }
    setStage("analyzing");
    setError("");
    setNeedsVehicle(false);
    try {
      const up = await uploadImages(files);
      const result = await analyzeUpload(up.upload_id, {
        vin: vin || undefined,
        make: make || undefined,
        model: model || undefined,
        year: year ? Number(year) : undefined,
        useConsensus,
      });
      if ((result as { status: string }).status === "vehicle_confirmation_needed") {
        setNeedsVehicle(true);
        setStage("form");
        return;
      }
      setReport(result);
      setStage("result");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
      setStage("form");
    }
  }

  function reset() {
    setStage("form");
    setFiles([]);
    setReport(null);
    setError("");
    setNeedsVehicle(false);
    setVin("");
    setMake("");
    setModel("");
    setYear("");
    setUseConsensus(false);
  }

  if (stage === "result" && report) return <DamageReport report={report} onReset={reset} />;

  if (stage === "analyzing") {
    return (
      <p className="typing" role="status">
        Analyzing {files.length} photo{files.length === 1 ? "" : "s"}. This usually takes 15 to 30 seconds
        <span className="typing__cursor" aria-hidden="true" />
      </p>
    );
  }

  return (
    <form onSubmit={handleAnalyze} noValidate>
      <h1 className="form-title">Damage report</h1>
      <p className="lede">
        Add photos of the damaged car. Faces and number plates are blurred before anything is analysed. You get the
        damaged parts, whether to repair or replace each one, and a parts-and-labour estimate.
      </p>

      {error && (
        <div className="note note--alarm" role="alert">
          <p className="note__title">Analysis failed</p>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}
      {needsVehicle && (
        <div className="note" role="alert">
          <p className="note__title">Which car is this?</p>
          <p style={{ margin: 0 }}>
            The photos didn&apos;t show the vehicle clearly enough to identify it. Fill in the make, model and year
            below, then analyze again.
          </p>
        </div>
      )}

      <section className="section" aria-labelledby="photos-label">
        <h2 className="section__label" id="photos-label">
          <span className="section__letter">A.</span> Photos
        </h2>
        <UploadZone files={files} onFiles={setFiles} />
      </section>

      <section className="section" aria-labelledby="vehicle-label">
        <h2 className="section__label" id="vehicle-label">
          <span className="section__letter">B.</span> Vehicle
          <span className="section__hint">Optional. The AI identifies the car if you leave this blank.</span>
        </h2>
        <div className="fields">
          <div className="field field--wide">
            <label htmlFor="vin">VIN (most accurate)</label>
            <input
              id="vin"
              value={vin}
              onChange={(e) => setVin(e.target.value.toUpperCase())}
              maxLength={17}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="field">
            <label htmlFor="make">Make</label>
            <input id="make" value={make} onChange={(e) => setMake(e.target.value)} placeholder="Toyota" />
          </div>
          <div className="field">
            <label htmlFor="model">Model</label>
            <input id="model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="Corolla" />
          </div>
          <div className="field">
            <label htmlFor="year">Year</label>
            <input
              id="year"
              value={year}
              onChange={(e) => setYear(e.target.value.replace(/\D/g, "").slice(0, 4))}
              inputMode="numeric"
              placeholder="2018"
            />
          </div>
        </div>
        <label className="check">
          <input type="checkbox" checked={useConsensus} onChange={(e) => setUseConsensus(e.target.checked)} />
          <span>Check with a second AI provider (about twice as slow)</span>
        </label>
      </section>

      <div className="actions">
        <button type="submit" className="button">
          Analyze damage
        </button>
        {files.length > 0 && (
          <button type="button" className="link-button" onClick={reset}>
            Start over
          </button>
        )}
      </div>
    </form>
  );
}
