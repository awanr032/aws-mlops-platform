"""Handler tests with a fake Bedrock client; no AWS account needed."""

import json

import pytest
from botocore.exceptions import ClientError

import handlers
from extraction import InvalidInput


class FakeBedrock:
    def __init__(self, reply=None, error_code=None):
        self.reply = reply
        self.error_code = error_code
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error_code:
            raise ClientError({"Error": {"Code": self.error_code, "Message": "x"}}, "Converse")
        return {
            "output": {"message": {"content": [{"text": self.reply}]}},
            "usage": {"inputTokens": 180, "outputTokens": 40},
            "metrics": {"latencyMs": 420},
        }


@pytest.fixture(autouse=True)
def model_env(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "mistral.ministral-3-14b-instruct")


def test_validate_input_uses_execution_name_when_no_id_given():
    result = handlers.validate_input({"input": {"text": "P-101 leak"}, "execution_name": "run-1"}, None)
    assert result == {"work_order_id": "run-1", "text": "P-101 leak"}


def test_validate_input_raises_invalid_input_by_name():
    with pytest.raises(InvalidInput):
        handlers.validate_input({"input": {"text": ""}}, None)
    assert InvalidInput.__name__ == "InvalidInput"  # the workflow catches this exact name


def test_extract_sends_prompt_and_returns_raw_text_and_usage():
    fake = FakeBedrock(reply='{"asset": "P-101"}')
    result = handlers.extract({"text": "P-101 leak"}, None, client=fake)

    call = fake.calls[0]
    assert call["modelId"] == "mistral.ministral-3-14b-instruct"
    assert call["inferenceConfig"]["temperature"] == 0
    assert "P-101 leak" in call["messages"][0]["content"][0]["text"]
    assert result == {
        "raw": '{"asset": "P-101"}',
        "model_id": "mistral.ministral-3-14b-instruct",
        "input_tokens": 180,
        "output_tokens": 40,
    }


@pytest.mark.parametrize("code", ["ThrottlingException", "ServiceUnavailableException"])
def test_busy_model_raises_retryable_error(code):
    with pytest.raises(handlers.ModelBusy):
        handlers.extract({"text": "x"}, None, client=FakeBedrock(error_code=code))


def test_permission_problem_is_not_retried():
    with pytest.raises(handlers.ModelCallFailed):
        handlers.extract({"text": "x"}, None, client=FakeBedrock(error_code="AccessDeniedException"))


def test_check_output_accepts_a_good_answer():
    raw = json.dumps({
        "asset": "P-101", "component": "mechanical seal", "fault": "leak",
        "action": "replaced gasket", "downtime_hours": 3,
    })
    result = handlers.check_output({"raw": raw, "text": "P-101 leaking at mech seal"}, None)
    assert result["valid"] is True and result["problems"] == []


def test_check_output_sends_broken_answers_to_review():
    result = handlers.check_output({"raw": "Sorry, I can't.", "text": "P-101 leak"}, None)
    assert result == {"valid": False, "entities": {}, "problems": ["no JSON object found in the model answer"]}
