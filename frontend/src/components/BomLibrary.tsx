import { useState } from "react";
import BomUpload from "./BomUpload";
import type { BOM } from "../api";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function BomLibrary({ boms, onSelect, onCreated }: { boms: BOM[]; onSelect: (bom: BOM) => void; onCreated: (bom: BOM) => void }) {
  const [showForm, setShowForm] = useState(boms.length === 0);

  return (
    <div>
      {showForm ? (
        <BomUpload
          onBomReady={(bom) => {
            onCreated(bom);
            setShowForm(false);
          }}
        />
      ) : (
        <button type="button" className="btn btn--ghost" onClick={() => setShowForm(true)}>
          + Load a new BOM
        </button>
      )}

      <div className="bom-grid">
        {boms.length === 0 && !showForm && (
          <p className="step__waiting">No BOMs loaded yet. Load one above to start checking certificates against it.</p>
        )}
        {boms.map((bom) => (
          <button key={bom.bom_id} type="button" className="bom-card" onClick={() => onSelect(bom)}>
            <span className="bom-card__project">{bom.project_id}</span>
            <span className="bom-card__name">{bom.filename}</span>
            <span className="bom-card__meta">
              Rev {bom.version} · {bom.items.length} items · loaded {formatDate(bom.uploaded_at)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
