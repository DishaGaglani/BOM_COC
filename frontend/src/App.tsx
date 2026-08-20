import { useEffect, useState } from "react";
import BomLibrary from "./components/BomLibrary";
import CocUpload from "./components/CocUpload";
import ValidationReport from "./components/ValidationReport";
import { listBOMs, listCOCs, type BOM, type COC } from "./api";
import "./App.css";

function overallStatus(coc: COC): "PASS" | "FAIL" | "WARNING" {
  const statuses = coc.validations.map((v) => v.status);
  if (statuses.includes("FAIL")) return "FAIL";
  if (statuses.includes("WARNING")) return "WARNING";
  return "PASS";
}

function App() {
  const [boms, setBoms] = useState<BOM[]>([]);
  const [selectedBom, setSelectedBom] = useState<BOM | null>(null);
  const [cocs, setCocs] = useState<COC[]>([]);
  const [loadingCocs, setLoadingCocs] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  useEffect(() => {
    listBOMs()
      .then(setBoms)
      .catch((err) => setLibraryError(err instanceof Error ? err.message : "Couldn't reach the backend."));
  }, []);

  const selectBom = (bom: BOM) => {
    setSelectedBom(bom);
    setLoadingCocs(true);
    listCOCs(bom.bom_id)
      .then(setCocs)
      .catch(() => setCocs([]))
      .finally(() => setLoadingCocs(false));
  };

  const backToLibrary = () => {
    setSelectedBom(null);
    setCocs([]);
  };

  const counts = cocs.reduce(
    (acc, coc) => {
      acc[overallStatus(coc)]++;
      return acc;
    },
    { PASS: 0, FAIL: 0, WARNING: 0 }
  );

  return (
    <div className="ledger">
      <header className="title-block">
        <div className="title-block__mark">
          <span>COC</span>
        </div>
        <div>
          <h1>Traceability Ledger</h1>
          <p className="title-block__meta">Runs on this machine — Postgres + local Ollama, no external API calls</p>
        </div>
      </header>

      {!selectedBom ? (
        <>
          <p className="section-eyebrow">Step 01 — reference documents</p>
          {libraryError && <p className="error">{libraryError}</p>}
          <BomLibrary
            boms={boms}
            onCreated={(bom) => setBoms((prev) => [bom, ...prev])}
            onSelect={selectBom}
          />
        </>
      ) : (
        <>
          <button type="button" className="btn btn--ghost back-link" onClick={backToLibrary}>
            ← All BOMs
          </button>

          <div className="panel bom-chip">
            <div className="bom-chip__icon">✓</div>
            <div>
              <div className="bom-chip__name">{selectedBom.filename}</div>
              <div className="bom-chip__detail">
                {selectedBom.project_id} · Rev {selectedBom.version} · {selectedBom.items.length} line items
              </div>
            </div>
          </div>

          <div className="workspace-coc">
            <CocUpload bom={selectedBom} onCocsValidated={(newCocs) => setCocs((prev) => [...newCocs, ...prev])} />
          </div>

          {loadingCocs && <p className="panel__hint">Loading previously checked certificates…</p>}

          {!loadingCocs && cocs.length > 0 && (
            <section className="results-section">
              <div className="ledger-results__head">
                <h2>Results</h2>
                <div className="stat-strip">
                  <div className="stat">
                    <span className="stat__count">{cocs.length}</span>
                    <span className="stat__label">checked</span>
                  </div>
                  <div className="stat stat--pass">
                    <span className="stat__count">{counts.PASS}</span>
                    <span className="stat__label">pass</span>
                  </div>
                  <div className="stat stat--fail">
                    <span className="stat__count">{counts.FAIL}</span>
                    <span className="stat__label">fail</span>
                  </div>
                  <div className="stat stat--warn">
                    <span className="stat__count">{counts.WARNING}</span>
                    <span className="stat__label">review</span>
                  </div>
                </div>
              </div>

              <div className="ledger-results">
                {cocs.map((coc) => (
                  <ValidationReport key={coc.coc_id} coc={coc} />
                ))}
              </div>
            </section>
          )}

          {!loadingCocs && cocs.length === 0 && (
            <p className="step__waiting results-section">No certificates checked against this BOM yet. Add one above.</p>
          )}
        </>
      )}
    </div>
  );
}

export default App;
