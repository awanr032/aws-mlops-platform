"""Scoring the RAG system against questions with known answers. No AWS code here.

Four measures:
  retrieval  did the right manual section appear among the retrieved sources?
  citation   did the answer cite that section?
  fact       does the answer contain the key fact (e.g. "45 Nm")?
  refusal    for questions the manuals can't answer, did it say so instead of guessing?
"""

from __future__ import annotations

GATE = {"retrieval": 0.8, "citation": 0.7, "fact": 0.7, "refusal": 0.5}


def _norm(text: str) -> str:
    return " ".join(text.lower().replace(",", "").replace(" ", " ").split())


def _matches(entry: dict, case: dict) -> bool:
    return entry.get("source") == case["source"] and entry.get("section") == case["section"]


def score_case(case: dict, response: dict) -> dict:
    if case.get("not_in_manuals"):
        return {"refusal": response.get("found") is False}
    answer = response.get("answer", "") if response.get("found") else ""
    return {
        "retrieval": any(_matches(s, case) for s in response.get("sources", [])),
        "citation": any(_matches(c, case) for c in response.get("citations", [])),
        "fact": _norm(case["fact"]) in _norm(answer),
    }


def summarise(scored: list[dict]) -> dict:
    """Rate per measure over the cases it applies to, and whether each passes the gate."""
    rates = {}
    for measure in GATE:
        values = [s[measure] for s in scored if measure in s]
        rates[measure] = round(sum(values) / len(values), 3) if values else None
    failures = [f"{m} {rates[m]} < {GATE[m]}" for m in GATE if rates[m] is not None and rates[m] < GATE[m]]
    return {"rates": rates, "passed": not failures, "failures": failures}
