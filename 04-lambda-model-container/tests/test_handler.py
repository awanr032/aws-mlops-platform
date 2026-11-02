import importlib

import pytest

import features

HEALTHY = {"rms": 0.28, "kurtosis": 3.1, "crest_factor": 3.4, "peak_freq_hz": 30.0, "shaft_speed_hz": 30.0}
INNER = {"rms": 0.9, "kurtosis": 7.4, "crest_factor": 6.3, "peak_freq_hz": 162.0, "shaft_speed_hz": 30.0}
OUTER = {"rms": 0.72, "kurtosis": 6.1, "crest_factor": 5.7, "peak_freq_hz": 108.0, "shaft_speed_hz": 30.0}


@pytest.fixture
def handler(model_dir, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", model_dir)
    monkeypatch.setenv("MODEL_VERSION", "test-sha")
    import handler as module

    return importlib.reload(module)  # fresh module = a cold start


def test_single_reading_is_classified(handler):
    result = handler.lambda_handler(INNER, None)
    assert result["prediction"]["condition"] == "inner_race_fault"
    assert 0 < result["prediction"]["confidence"] <= 1
    assert abs(sum(result["prediction"]["probabilities"].values()) - 1) < 0.01
    assert result["model"]["version"] == "test-sha"


def test_batch_of_readings(handler):
    result = handler.lambda_handler({"readings": [HEALTHY, INNER, OUTER]}, None)
    assert [p["condition"] for p in result["predictions"]] == [
        "healthy", "inner_race_fault", "outer_race_fault",
    ]


def test_first_call_is_a_cold_start_and_later_calls_are_warm(handler):
    first = handler.lambda_handler(HEALTHY, None)
    second = handler.lambda_handler(HEALTHY, None)
    assert first["cold_start"] is True and "model_load_ms" in first
    assert second["cold_start"] is False and "model_load_ms" not in second


def test_bad_request_returns_an_error_without_loading_the_model(handler):
    result = handler.lambda_handler({"rms": 0.3}, None)
    assert "missing" in result["error"]
    assert handler._model is None


@pytest.mark.parametrize(
    "reading, message",
    [
        ({**HEALTHY, "rms": "high"}, "rms must be a number"),
        ({**HEALTHY, "kurtosis": True}, "kurtosis must be a number"),
        ({**HEALTHY, "rms": float("nan")}, "rms must be a number"),
        ({**HEALTHY, "peak_freq_hz": -5}, "outside the plausible range"),
        ({**HEALTHY, "shaft_speed_hz": 0}, "outside the plausible range"),
        ([1, 2, 3], "JSON object"),
    ],
)
def test_reading_validation(reading, message):
    with pytest.raises(features.BadRequest, match=message):
        features.parse_reading(reading)


def test_batch_limits():
    with pytest.raises(features.BadRequest, match="non-empty"):
        features.parse_request({"readings": []})
    with pytest.raises(features.BadRequest, match="at most 100"):
        features.parse_request({"readings": [HEALTHY] * 101})
    with pytest.raises(features.BadRequest, match=r"readings\[1\]"):
        features.parse_request({"readings": [HEALTHY, {"rms": 1}]})
