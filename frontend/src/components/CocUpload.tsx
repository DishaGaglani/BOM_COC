import { useState } from "react";
import { uploadCOCs, type BOM, type COC } from "../api";

export default function CocUpload({ bom, onCocsValidated }: { bom: BOM; onCocsValidated: (cocs: COC[]) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const cocs = await uploadCOCs(bom.bom_id, files);
      onCocsValidated(cocs);
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't check these certificates. Try again in a moment.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="panel">
      <p className="panel__eyebrow">Checked against {bom.filename}</p>
      <h2>Add certificates to check</h2>
      <p className="panel__hint">One at a time, or drop a batch — each is matched to a BOM line item by part ID or PO number.</p>

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
          const dropped = Array.from(e.dataTransfer.files ?? []);
          if (dropped.length) setFiles(dropped);
        }}
      >
        <input type="file" accept=".pdf" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} required />
        {files.length > 0 ? (
          <span className="dropzone__filename">
            {files.length} file{files.length === 1 ? "" : "s"} selected
          </span>
        ) : (
          <span>Drop COC PDF(s) here, or click to choose</span>
        )}
      </label>

      <button type="submit" className="btn" disabled={loading || files.length === 0}>
        {loading ? "Checking…" : `Check ${files.length || ""} certificate${files.length === 1 ? "" : "s"}`}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
