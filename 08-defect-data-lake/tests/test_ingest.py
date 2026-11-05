import io

import ingest
from conftest import make_line


def test_choose_first_existing_file_per_start_year():
    existing = {ingest.chunk_url("2020-2024"): 400_000_000, ingest.chunk_url("2025-2026"): 90_000_000,
                ingest.chunk_url("2025-2025"): 50_000_000}
    chosen = ingest.choose_chunks(["2020-2024", "2025-2029", "2025-2026", "2025-2025"], probe=existing.get)
    assert chosen == [("2020-2024", 400_000_000), ("2025-2026", 90_000_000)]


def test_nothing_found():
    assert ingest.choose_chunks(["1999-2003"], probe=lambda url: None) == []


def test_decode_utf8_and_windows_1252():
    assert ingest.decode("CAFÉ".encode("utf-8")) == ("CAFÉ", False)
    assert ingest.decode("CAFÉ".encode("cp1252")) == ("CAFÉ", True)


def test_normalise_counts_lines_fields_and_conversions():
    source = io.BytesIO(
        (make_line() + "\r\n").encode("utf-8")
        + (make_line(49, cdescr="BRAKE FAILURE AT 50 MPH – CAFÉ") + "\n").encode("cp1252")
        + b"\n")
    target = io.StringIO()
    stats = ingest.normalise(source, target)
    assert stats == {"lines": 2, "lines_converted_from_cp1252": 1, "fields_per_line": {"49": 1, "51": 1}}
    assert "CAFÉ" in target.getvalue() and "\r" not in target.getvalue()
