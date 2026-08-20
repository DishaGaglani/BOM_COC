const CLASS: Record<string, string> = {
  PASS: "stamp stamp--pass",
  FAIL: "stamp stamp--fail",
  WARNING: "stamp stamp--warning",
};

const LABEL: Record<string, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  WARNING: "Review",
};

export default function StatusBadge({ status }: { status: string }) {
  return <span className={CLASS[status] ?? "stamp"}>{LABEL[status] ?? status}</span>;
}
