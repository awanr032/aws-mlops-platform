import pytest

from extraction import InvalidInput, check_entities, clean_input, parse_model_output

TEXT = "P-101 leaking at mech seal, replaced gasket, 3hrs downtime"
GOOD = {
    "asset": "P-101",
    "component": "mechanical seal",
    "fault": "leak",
    "action": "replaced gasket",
    "downtime_hours": 3,
}


# --- input -----------------------------------------------------------------

def test_clean_input_collapses_whitespace():
    assert clean_input({"text": "  P-101\n leaking  "})["text"] == "P-101 leaking"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "required"),
        ({"text": "   "}, "required"),
        ({"text": 42}, "required"),
        ({"text": "x" * 2001}, "at most"),
        ({"text": "ok", "work_order_id": ""}, "work_order_id"),
        ("not a dict", "JSON object"),
    ],
)
def test_clean_input_rejects_bad_input(payload, message):
    with pytest.raises(InvalidInput, match=message):
        clean_input(payload)


# --- parsing the model's reply ---------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        '{"asset": "P-101"}',
        '```json\n{"asset": "P-101"}\n```',
        'Here is the answer:\n{"asset": "P-101"}\nHope this helps!',
    ],
)
def test_json_is_found_even_when_the_model_adds_extra_text(raw):
    data, problem = parse_model_output(raw)
    assert problem is None and data == {"asset": "P-101"}


@pytest.mark.parametrize(
    "raw, message",
    [
        ("", "empty"),
        ("I cannot help with that.", "no JSON"),
        ('{"asset": "P-101",}', "not valid JSON"),
    ],
)
def test_unusable_model_replies_are_reported(raw, message):
    data, problem = parse_model_output(raw)
    assert data is None and message in problem


# --- checking the fields ---------------------------------------------------

def test_good_answer_passes():
    entities, problems = check_entities(GOOD, TEXT)
    assert problems == []
    assert entities["downtime_hours"] == 3.0


def test_invented_asset_is_flagged():
    _, problems = check_entities({**GOOD, "asset": "P-999"}, TEXT)
    assert "asset 'P-999' does not appear in the text" in problems


def test_asset_match_ignores_case_spaces_and_hyphens():
    _, problems = check_entities({**GOOD, "asset": "p 101"}, TEXT)
    assert problems == []


def test_missing_keys_are_reported():
    _, problems = check_entities({"asset": "P-101", "fault": "leak"}, TEXT)
    assert any(p.startswith("missing keys") for p in problems)


def test_wrong_types_are_reported():
    _, problems = check_entities({**GOOD, "component": ["seal"], "downtime_hours": "lots"}, TEXT)
    assert "component must be a string or null" in problems
    assert "downtime_hours must be a number or null" in problems


def test_placeholder_words_count_as_empty():
    entities, _ = check_entities({**GOOD, "action": "N/A"}, TEXT)
    assert entities["action"] is None


def test_text_with_no_maintenance_content_needs_review():
    empty = {"asset": None, "component": None, "fault": None, "action": None, "downtime_hours": None}
    _, problems = check_entities(empty, "Team lunch moved to Friday")
    assert any("no maintenance information" in p for p in problems)


def test_work_order_must_say_which_equipment():
    vague = {"asset": None, "component": None, "fault": None, "action": "checked", "downtime_hours": None}
    _, problems = check_entities(vague, "Checked it, all fine")
    assert any("no equipment identified" in p for p in problems)


def test_component_alone_is_enough_equipment():
    entry = {"asset": None, "component": "belt", "fault": "misaligned", "action": None, "downtime_hours": None}
    _, problems = check_entities(entry, "belt misaligned")
    assert problems == []


def test_impossible_downtime_is_rejected():
    _, problems = check_entities({**GOOD, "downtime_hours": -2}, TEXT)
    assert "downtime_hours must be between 0 and 8760" in problems
