import prompts

HITS = [
    ({"title": "P-200 Pump", "section": "6.3 Bearing housing", "source": "p200", "text": "Tighten to 45 Nm."}, 0.71),
    ({"title": "G-40 Gearbox", "section": "3 Installation", "source": "g40", "text": "Coupling 85 Nm."}, 0.52),
]


def test_user_message_numbers_sources_and_ends_with_question():
    msg = prompts.build_user_message("Torque?", HITS)
    assert "[S1] P-200 Pump | 6.3 Bearing housing\nTighten to 45 Nm." in msg
    assert "[S2] G-40 Gearbox | 3 Installation" in msg
    assert msg.endswith("Question: Torque?")


def test_answer_with_valid_citation():
    result = prompts.parse_answer("Tighten the bolts to 45 Nm in a cross pattern [S1].", HITS)
    assert result["found"] and not result["warnings"]
    assert [c["section"] for c in result["citations"]] == ["6.3 Bearing housing"]
    assert result["citations"][0]["score"] == 0.71


def test_repeated_citations_listed_once_in_order():
    result = prompts.parse_answer("A [S2]. B [S1]. C [S2].", HITS)
    assert [c["ref"] for c in result["citations"]] == ["S2", "S1"]


def test_invented_citation_is_removed_and_flagged():
    result = prompts.parse_answer("It is 45 Nm [S1][S7].", HITS)
    assert result["answer"] == "It is 45 Nm [S1]."
    assert "S7" in result["warnings"][0]


def test_uncited_answer_is_flagged():
    result = prompts.parse_answer("It is 45 Nm.", HITS)
    assert result["found"] and "no citations" in result["warnings"][0]


def test_refusal_variants():
    for raw in ["NOT_FOUND", "NOT_FOUND.", "  not_found  ", "NOT_FOUND - not in sources", ""]:
        result = prompts.parse_answer(raw, HITS)
        assert result["found"] is False and result["answer"] == prompts.NOT_FOUND_ANSWER


def test_system_prompt_states_the_rules():
    for rule in ["ONLY", "cite", "exactly", prompts.NOT_FOUND]:
        assert rule in prompts.SYSTEM_PROMPT
