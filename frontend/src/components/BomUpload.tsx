import { useState } from "react";
import { uploadBOM, type BOM } from "../api";

export default function BomUpload({ onBomReady }: { onBomReady: (bom: BOM) => void }) {
  const [projectId, setProjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !projectId) return;
    setLoading(true);
    setError(null);
    try {
      const bom = await uploadBOM(projectId, file);
      onBomReady(bom);
      setFile(null);
      setProjectId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't read this PDF. Check it's the traceability matrix, not a scanned copy.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="panel">
      <p className="panel__eyebrow">New reference document</p>
      <h2>Load a BOM or traceability matrix</h2>
      <p className="panel__hint">Every certificate checked against this BOM is measured against its line items.</p>

      <label
        className={`dropzone${dragOver ? " dropzone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) setFile(dropped);
        }}
      >
        <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        {file ? <span className="dropzone__filename">{file.name}</span> : <span>Drop the BOM PDF here, or click to choose one</span>}
      </label>

      <label className="field">
        Project ID
        <input type="text" value={projectId} onChange={(e) => setProjectId(e.target.value)} placeholder="e.g. PRJ-2026-014" required />
      </label>

      <button type="submit" className="btn" disabled={loading}>
        {loading ? "Reading BOM…" : "Load BOM"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
