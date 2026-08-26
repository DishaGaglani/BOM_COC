from app.parameters.html_table import parse_html_table


def test_parses_simple_table():
    html = "<table><tr><td>Part No</td><td>Qty</td></tr><tr><td>ABC-1</td><td>10</td></tr></table>"
    assert parse_html_table(html) == [["Part No", "Qty"], ["ABC-1", "10"]]


def test_th_cells_are_captured_like_td():
    html = "<table><tr><th>Part No</th><th>Qty</th></tr></table>"
    assert parse_html_table(html) == [["Part No", "Qty"]]


def test_empty_cells_preserved_as_empty_strings():
    html = "<table><tr><td>ABC-1</td><td></td></tr></table>"
    assert parse_html_table(html) == [["ABC-1", ""]]
