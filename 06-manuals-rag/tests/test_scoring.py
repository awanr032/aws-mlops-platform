import json
import os

from scoring import score_case, summarise

CASE = {"question": "Torque?", "source": "p200", "section": "6.3 Bearing housing", "fact": "45 Nm"}
GOOD = {"found": True, "answer": "Tighten to 45 Nm [S1].",
        "sources": [{"source": "p200", "section": "6.3 Bearing housing"}],
        "citations": [{"source": "p200", "section": "6.3 Bearing housing"}]}


def test_perfect_answer():
    assert score_case(CASE, GOOD) == {"retrieval": True, "citation": True, "fact": True}


def test_retrieved_but_wrong_fact_and_wrong_citation():
    response = {**GOOD, "answer": "Tighten to 85 Nm [S2].",
                "citations": [{"source": "g40", "section": "3 Installation"}]}
    assert score_case(CASE, response) == {"retrieval": True, "citation": False, "fact": False}


def test_fact_matching_ignores_case_and_thousands_commas():
    case = {**CASE, "fact": "2,000"}
    assert score_case(case, {**GOOD, "answer": "Every 2000 hours [S1]."})["fact"]


def test_refusal_cases():
    case = {"question": "Warranty?", "not_in_manuals": True}
    assert score_case(case, {"found": False}) == {"refusal": True}
    assert score_case(case, {"found": True, "answer": "Two years."}) == {"refusal": False}


def test_summary_and_gate():
    scored = [{"retrieval": True, "citation": True, "fact": True}] * 4 + [{"refusal": True}]
    assert summarise(scored)["passed"]
    scored.append({"retrieval": False, "citation": False, "fact": False})
    scored += [{"retrieval": False, "citation": False, "fact": False}]
    result = summarise(scored)
    assert not result["passed"] and result["rates"]["retrieval"] == round(4 / 6, 3)


def test_questions_file_points_at_real_sections(manuals):
    from chunking import chunk_markdown

    sections = {(c["source"], c["section"])
                for key, (text, _e) in manuals.items()
                for c in chunk_markdown(text, os.path.splitext(os.path.basename(key))[0])}
    here = os.path.dirname(__file__)
    cases = json.load(open(os.path.join(here, "..", "eval", "questions.json")))
    assert len(cases) >= 10
    for case in cases:
        if not case.get("not_in_manuals"):
            assert (case["source"], case["section"]) in sections, case["question"]
            # the key fact really is in that section
            text = " ".join(c["text"] for key, (t, _e) in manuals.items()
                            for c in chunk_markdown(t, os.path.splitext(os.path.basename(key))[0])
                            if (c["source"], c["section"]) == (case["source"], case["section"]))
            assert case["fact"].lower() in text.lower(), case["question"]
