"""Parse a single document from the command line, without running the API.

Usage:
    python scripts/parse_file.py /path/to/file.pdf [strategy]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsing.unstructured_parser import parse_document  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    file_path = Path(sys.argv[1])
    strategy = sys.argv[2] if len(sys.argv) > 2 else None

    document = parse_document(file_path, file_path.name, strategy=strategy)
    print(
        f"filename={document.filename} strategy_used={document.strategy_used} "
        f"elements={document.element_count} tables={document.table_count} "
        f"warnings={document.warnings}"
    )
    print(json.dumps(document.model_dump(mode="json"), indent=2)[:4000])


if __name__ == "__main__":
    main()
