from datetime import date

import pytest

from validate import FileRejected, to_csv, validate_csv

TODAY = date(2026, 10, 19)
HEADER = "asset_id,date,priority,description\n"


def test_example_file_from_the_explanation():
    text = HEADER + (
        "P-101,2026-10-01,high,Leaking seal\n"
        "P-102,2026-10-02,low,Routine check\n"
        ",2026-10-03,medium,Noisy bearing\n"
        "P-104,31/02/2026,high,Motor overheating\n"
        "P-105,2026-10-05,urgent,Valve stuck\n"
    )
    result = validate_csv(text, TODAY)
    assert [r["asset_id"] for r in result.accepted] == ["P-101", "P-102"]
    errors = {r["row_number"]: r["error"] for r in result.rejected}
    assert errors[4] == "missing asset_id"
    assert "not in YYYY-MM-DD format" in errors[5]
    assert "priority 'urgent'" in errors[6]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("P-1,2026-02-30,low,x", "does not exist"),
        ("P-1,2027-01-01,low,x", "in the future"),
        ("P-1,2026-10-01,,x", "priority '(empty)'"),
        ("P-1,2026-10-01,low,", "missing description"),
        ("P-1,,low,x", "missing date"),
    ],
)
def test_row_problems_are_explained(line, expected):
    result = validate_csv(HEADER + line + "\n", TODAY)
    assert not result.accepted
    assert expected in result.rejected[0]["error"]


def test_all_problems_in_a_row_are_reported_together():
    result = validate_csv(HEADER + ",bad,urgent,\n", TODAY)
    error = result.rejected[0]["error"]
    assert error.count(";") == 3  # four separate problems


def test_priority_is_case_insensitive_and_normalised():
    result = validate_csv(HEADER + "P-1,2026-10-01,HIGH,x\n", TODAY)
    assert result.accepted[0]["priority"] == "high"


def test_header_is_case_and_space_insensitive_and_bom_is_ignored():
    text = "﻿ Asset_ID , Date,PRIORITY,description\nP-1,2026-10-01,low,x\n"
    assert len(validate_csv(text, TODAY).accepted) == 1


def test_optional_downtime_column_is_checked_and_kept():
    text = "asset_id,date,priority,description,downtime_hours\n" \
           "P-1,2026-10-01,low,x,2.5\nP-2,2026-10-01,low,x,-1\nP-3,2026-10-01,low,x,abc\n"
    result = validate_csv(text, TODAY)
    assert result.columns[-1] == "downtime_hours"
    assert len(result.accepted) == 1
    assert "between 0" in result.rejected[0]["error"]
    assert "not a number" in result.rejected[1]["error"]


def test_blank_lines_are_skipped():
    result = validate_csv(HEADER + "P-1,2026-10-01,low,x\n\n,,,\n", TODAY)
    assert result.total == 1


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "empty"),
        ("asset_id,date,description\nP-1,2026-10-01,x\n", "missing required columns: priority"),
        (HEADER, "no data rows"),
    ],
)
def test_whole_file_problems(text, message):
    with pytest.raises(FileRejected, match=message):
        validate_csv(text, TODAY)


def test_to_csv_round_trip():
    text = to_csv([{"a": "1", "b": "x,y"}], ["a", "b"])
    assert text == 'a,b\n1,"x,y"\n'
