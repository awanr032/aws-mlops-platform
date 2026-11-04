"""The instructions for the model, and checking its answer. No AWS code here."""

from __future__ import annotations

import re

NOT_FOUND = "NOT_FOUND"
NOT_FOUND_ANSWER = "I can't find this in the maintenance manuals."

SYSTEM_PROMPT = f"""You answer questions from maintenance engineers using ONLY the numbered sources provided.

Rules:
- Use only facts stated in the sources. Do not use outside knowledge, even if you are sure.
- After every sentence that states a fact, cite its source in square brackets, e.g. [S1] or [S1][S3].
- Copy numbers (torques, intervals, temperatures, limits) exactly as written, with their units.
- If the sources are about a different machine than the one asked about, they do not answer the question.
- If the sources do not contain the answer, reply with exactly: {NOT_FOUND}
- Keep the answer short: at most 5 sentences, no introduction."""

CITATION = re.compile(r"\[S(\d+)\]")


def build_user_message(question: str, hits: list[tuple[dict, float]]) -> str:
    parts = ["Sources:"]
    for n, (chunk, _score) in enumerate(hits, start=1):
        parts.append(f"[S{n}] {chunk['title']} | {chunk['section']}\n{chunk['text']}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def source_entry(n: int, chunk: dict, score: float) -> dict:
    return {"ref": f"S{n}", "title": chunk["title"], "section": chunk["section"],
            "source": chunk["source"], "score": score}


def parse_answer(raw: str, hits: list[tuple[dict, float]]) -> dict:
    """Check the model's reply: refusal, valid citations, invented citation numbers."""
    text = raw.strip()
    if not text or text.strip(" .").upper() == NOT_FOUND or (NOT_FOUND in text and len(text) < 40):
        return {"found": False, "answer": NOT_FOUND_ANSWER, "citations": [], "warnings": []}

    warnings = []
    used = []
    for number in CITATION.findall(text):
        n = int(number)
        if 1 <= n <= len(hits):
            if n not in used:
                used.append(n)
        else:
            warnings.append(f"model cited S{n}, which does not exist; removed")
    text = CITATION.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= len(hits) else "", text).strip()
    if not used:
        warnings.append("answer has no citations; treat with caution")
    return {
        "found": True,
        "answer": text,
        "citations": [source_entry(n, *hits[n - 1]) for n in used],
        "warnings": warnings,
    }
