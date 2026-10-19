"""Row-level checks for maintenance work-order CSV files. No AWS code here."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

REQUIRED_COLUMNS = ["asset_id", "date", "priority", "description"]
OPTIONAL_COLUMNS = ["technician", "downtime_hours"]
PRIORITIES = {"low", "medium", "high", "critical"}

MAX_ROWS = 50_000
MAX_ASSET_ID = 64
MAX_DESCRIPTION = 1000
MAX_DOWNTIME_HOURS = 8760  # one year

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FileRejected(Exception):
    """The whole file is unusable (wrong columns, empty, too many rows)."""


@dataclass
class Result:
    columns: list[str]
    accepted: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # each has row_number and error

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.rejected)


def _check_row(row: dict, today: date) -> list[str]:
    errors = []

    asset_id = row.get("asset_id", "")
    if not asset_id:
        errors.append("missing asset_id")
    elif len(asset_id) > MAX_ASSET_ID:
        errors.append(f"asset_id longer than {MAX_ASSET_ID} characters")

    raw_date = row.get("date", "")
    if not raw_date:
        errors.append("missing date")
    elif not DATE_PATTERN.match(raw_date):
        errors.append(f"date '{raw_date}' is not in YYYY-MM-DD format")
    else:
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            errors.append(f"date '{raw_date}' does not exist")
        else:
            if parsed > today:
                errors.append(f"date '{raw_date}' is in the future")

    priority = row.get("priority", "").lower()
    if priority not in PRIORITIES:
        shown = row.get("priority", "") or "(empty)"
        errors.append(f"priority '{shown}' must be one of {sorted(PRIORITIES)}")
    else:
        row["priority"] = priority

    description = row.get("description", "")
    if not description:
        errors.append("missing description")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(f"description longer than {MAX_DESCRIPTION} characters")

    downtime = row.get("downtime_hours", "")
    if downtime:
        try:
            hours = float(downtime)
        except ValueError:
            errors.append(f"downtime_hours '{downtime}' is not a number")
        else:
            if not 0 <= hours <= MAX_DOWNTIME_HOURS:
                errors.append(f"downtime_hours must be between 0 and {MAX_DOWNTIME_HOURS}")

    return errors


def validate_csv(text: str, today: date) -> Result:
    """Split a CSV into accepted and rejected rows, with a reason for each rejection."""
    text = text.lstrip("﻿")  # Excel often adds a byte-order mark
    if not text.strip():
        raise FileRejected("file is empty")

    reader = csv.DictReader(io.StringIO(text))
    header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise FileRejected(f"missing required columns: {', '.join(missing)}")
    reader.fieldnames = header

    columns = REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in header]
    result = Result(columns=columns)

    for line_number, raw in enumerate(reader, start=2):  # line 1 is the header
        if result.total >= MAX_ROWS:
            raise FileRejected(f"more than {MAX_ROWS} rows")
        row = {c: (raw.get(c) or "").strip() for c in columns}
        if not any(row.values()):
            continue  # blank line
        errors = _check_row(row, today)
        if errors:
            result.rejected.append({"row_number": line_number, "error": "; ".join(errors), **row})
        else:
            result.accepted.append(row)

    if result.total == 0:
        raise FileRejected("file has a header but no data rows")
    return result


def to_csv(rows: list[dict], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
