"""Prompt, parsing and checking for maintenance entity extraction. No AWS code here."""

from __future__ import annotations

import json
import re

FIELDS = ["asset", "component", "fault", "action", "downtime_hours"]
TEXT_FIELDS = ["asset", "component", "fault", "action"]
MAX_TEXT = 2000
MAX_FIELD = 200

SYSTEM_PROMPT = """You extract structured information from maintenance work-order text.

Return ONE JSON object and nothing else: no explanation, no markdown, no code fences.
Use exactly these keys:
  "asset":          the equipment identifier or name, copied exactly as written (e.g. "P-101"), or null
  "component":      the part of the equipment involved (e.g. "mechanical seal"), or null
  "fault":          the problem or symptom observed (e.g. "leak"), or null
  "action":         what the technician did (e.g. "replaced gasket"), or null
  "downtime_hours": hours of downtime as a number, or null

Rules:
- Only use information that is in the text. If something is not mentioned, use null.
- Expand obvious abbreviations ("mech seal" -> "mechanical seal", "brg" -> "bearing").
- Keep each value short: a few words, lower case except for asset identifiers.

Example
Text: C-7 brg noisy on DE, greased and monitored
Answer: {"asset": "C-7", "component": "bearing", "fault": "noise", "action": "greased and monitored", "downtime_hours": null}"""


class InvalidInput(Exception):
    """The work-order text cannot be sent to the model. Step Functions catches this by name."""


def clean_input(payload) -> dict:
    """Check the workflow input and return {"work_order_id", "text"}."""
    if not isinstance(payload, dict):
        raise InvalidInput("input must be a JSON object")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise InvalidInput("'text' is required and must be a non-empty string")
    text = " ".join(text.split())  # collapse newlines and repeated spaces
    if len(text) > MAX_TEXT:
        raise InvalidInput(f"'text' must be at most {MAX_TEXT} characters")

    work_order_id = payload.get("work_order_id")
    if work_order_id is not None and (not isinstance(work_order_id, str) or not work_order_id.strip()):
        raise InvalidInput("'work_order_id' must be a non-empty string when given")
    return {"work_order_id": (work_order_id or "").strip(), "text": text}


def build_messages(text: str) -> list[dict]:
    return [{"role": "user", "content": [{"text": f"Text: {text}\nAnswer:"}]}]


def parse_model_output(raw: str):
    """Pull the JSON object out of the model's reply. Returns (dict or None, problem or None)."""
    if not raw or not raw.strip():
        return None, "model returned an empty answer"
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None, "no JSON object found in the model answer"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return None, f"model answer is not valid JSON ({exc.msg})"
    if not isinstance(data, dict):
        return None, "model answer is not a JSON object"
    return data, None


def _normalise_identifier(value: str) -> str:
    return re.sub(r"[\s\-_]", "", value).lower()


def check_entities(data: dict, source_text: str):
    """Validate the model's fields. Returns (entities, problems).

    The model is treated like any other untrusted input: wrong types, missing keys,
    empty answers and invented asset IDs are all reported as problems.
    """
    problems = []
    entities = {}

    missing = [f for f in FIELDS if f not in data]
    if missing:
        problems.append(f"missing keys: {', '.join(missing)}")

    for field in TEXT_FIELDS:
        value = data.get(field)
        if value is None:
            entities[field] = None
        elif isinstance(value, str):
            value = value.strip()
            if not value or value.lower() in {"null", "none", "n/a", "unknown"}:
                entities[field] = None
            elif len(value) > MAX_FIELD:
                problems.append(f"{field} is longer than {MAX_FIELD} characters")
                entities[field] = value[:MAX_FIELD]
            else:
                entities[field] = value
        else:
            problems.append(f"{field} must be a string or null")
            entities[field] = None

    downtime = data.get("downtime_hours")
    if downtime is None or (isinstance(downtime, str) and not downtime.strip()):
        entities["downtime_hours"] = None
    else:
        try:
            hours = float(downtime)
        except (TypeError, ValueError):
            problems.append("downtime_hours must be a number or null")
            entities["downtime_hours"] = None
        else:
            if not 0 <= hours <= 8760:
                problems.append("downtime_hours must be between 0 and 8760")
                entities["downtime_hours"] = None
            else:
                entities["downtime_hours"] = hours

    # Grounding check: an asset ID that does not appear in the text was probably invented.
    asset = entities.get("asset")
    if asset and _normalise_identifier(asset) not in _normalise_identifier(source_text):
        problems.append(f"asset '{asset}' does not appear in the text")

    if not any(entities.get(f) for f in ("component", "fault", "action")):
        problems.append("no maintenance information found (component, fault and action are all empty)")
    elif not entities.get("asset") and not entities.get("component"):
        problems.append("no equipment identified (asset and component are both empty)")

    return entities, problems
