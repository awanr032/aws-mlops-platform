import pytest

import inference

HEALTHY = "0.3,3.0,3.5,30.0,30.0"
INNER = "0.9,7.4,6.3,162.0,30.0"


@pytest.fixture(scope="module")
def model(model_dir):
    return inference.model_fn(model_dir)


def test_full_request_cycle(model):
    body = f"{HEALTHY}\n{INNER}\n".encode()
    data = inference.input_fn(body, "text/csv")
    prediction = inference.predict_fn(data, model)
    out = inference.output_fn(prediction, "text/csv")
    lines = out.strip().split("\n")
    assert [line.split(",")[0] for line in lines] == ["healthy", "inner_race_fault"]
    assert all(0 < float(line.split(",")[1]) <= 1 for line in lines)


def test_one_output_line_per_input_line(model):
    data = inference.input_fn("\n".join([HEALTHY] * 7), "text/csv")
    assert len(inference.output_fn(inference.predict_fn(data, model), "text/csv").strip().split("\n")) == 7


def test_blank_lines_and_charset_are_fine():
    assert inference.input_fn(f"\n{HEALTHY}\n\n", "text/csv; charset=utf-8").shape == (1, 5)


@pytest.mark.parametrize("body, message", [
    ("0.3,3.0,3.5,30.0", "expected 5 values"),
    ("BRG-1,0.3,3.0,3.5,30.0,30.0", "expected 5 values"),
    ("0.3,high,3.5,30.0,30.0", "must be numbers"),
    ("\n\n", "Empty"),
])
def test_bad_input_is_a_clear_error(body, message):
    with pytest.raises(ValueError, match=message):
        inference.input_fn(body, "text/csv")


def test_only_csv_accepted():
    with pytest.raises(ValueError, match="Unsupported"):
        inference.input_fn('{"rms": 1}', "application/json")
