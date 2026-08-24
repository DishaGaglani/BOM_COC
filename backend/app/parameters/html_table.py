from html.parser import HTMLParser


class _TableHTMLParser(HTMLParser):
    """Minimal <table> -> rows-of-cell-text parser. Deliberately stdlib-only
    (no pandas.read_html/lxml dependency) since unstructured's table html is
    always a flat <table><tr><td>... structure, no nesting or attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell_parts is not None:
            if self._row is not None:
                self._row.append("".join(self._cell_parts).strip())
            self._cell_parts = None

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)


def parse_html_table(html: str) -> list[list[str]]:
    parser = _TableHTMLParser()
    parser.feed(html)
    return parser.rows
