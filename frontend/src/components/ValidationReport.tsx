import { useEffect, useState } from "react";
import { getReport, highlightedPdfUrl, type COC, type Report } from "../api";
import StatusBadge from "./StatusBadge";

const PARAMETER_LABEL: Record<string, string> = {
  document_type: "Document type",
  identity_field_presence: "Identity field",
  po_numbers: "PO number",
  part_id: "Part ID",
  model: "Model",
  serial_numbers: "Serial number",
  quantity: "Quantity",
  description: "Description",
  manufacturer: "Manufacturer",
  manufacturing_year: "Year of manufacture",
  warranty_expiry: "Warranty expiry",
  coc_issue_date: "COC issue date",
  signature: "Signature",
  seal: "Seal / stamp",
  test_certificate: "Test certificate",
  import_documents: "Import documents",
  authorization_letter: "Authorization letter",
};

export default function ValidationReport({ coc }: { coc: COC }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReport(coc.coc_id)
      .then(setReport)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load this report."));
  }, [coc.coc_id]);

  return (
    <div className="panel">
      <div className="entry-header">
        <h3>{coc.filename}</h3>
        {report && <StatusBadge status={report.overall_status} />}
        <a href={highlightedPdfUrl(coc.coc_id)} target="_blank" rel="noreferrer" className="pdf-link">
          Download annotated PDF ↗
        </a>
      </div>

      {error && <p className="error">{error}</p>}

      {report && (
        <table className="report-table">
          <thead>
            <tr>
              <th>Parameter</th>
              <th>Expected (BOM)</th>
              <th>Found (COC)</th>
              <th>Result</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((row, i) => (
              <tr key={i}>
                <td>{PARAMETER_LABEL[row.parameter] ?? row.parameter}</td>
                <td className="mono">{row.expected ?? "—"}</td>
                <td className="mono">{row.actual ?? "—"}</td>
                <td>
                  <StatusBadge status={row.status} />
                </td>
                <td className="reason">{row.reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
