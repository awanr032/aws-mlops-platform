import json

import pytest
from botocore.exceptions import ClientError

import bedrock
import query
from conftest import fake_embed


@pytest.fixture
def api(built, monkeypatch):
    """Question Lambda with the index and Bedrock replaced by local stand-ins."""
    store, manifest = built
    calls = {"generate": 0}

    def generate(system, user, max_tokens=500):
        calls["generate"] += 1
        calls["user"] = user
        return "Tighten them to 45 Nm in a cross pattern [S1]."

    monkeypatch.setattr(query, "get_store", lambda: (store, manifest))
    monkeypatch.setattr(bedrock, "embed", fake_embed)
    monkeypatch.setattr(bedrock, "generate", generate)
    return calls


def call(body):
    response = query.handler({"body": json.dumps(body)}, None)
    return response["statusCode"], json.loads(response["body"])


def test_answer_with_citation_and_sources(api):
    status, body = call({"question": "P-200 bearing housing bolts torque"})
    assert status == 200 and body["found"]
    assert body["citations"][0]["section"] == "6.3 Bearing housing"
    assert len(body["sources"]) == 4 and body["sources"][0]["ref"] == "S1"
    assert set(body["timings_ms"]) == {"index_load", "embed", "search", "generate", "total"}
    assert "Question: P-200 bearing housing bolts torque" in api["user"]


def test_retrieve_only_skips_the_model(api):
    status, body = call({"question": "P-200 bearing housing bolts torque", "retrieve_only": True, "top_k": 2})
    assert status == 200 and api["generate"] == 0
    assert len(body["sources"]) == 2 and "answer" not in body and "answer" not in body["models"]


def test_direct_invoke_without_api_gateway(api):
    response = query.handler({"question": "G-40 coupling bolts"}, None)
    assert response["statusCode"] == 200


@pytest.mark.parametrize("body, message", [
    ({}, "required"),
    ({"question": "hi"}, "required"),
    ({"question": "x" * 501}, "at most 500"),
    ({"question": "valid question", "top_k": 0}, "top_k"),
    ({"question": "valid question", "top_k": True}, "top_k"),
    ({"question": "valid question", "retrieve_only": "yes"}, "retrieve_only"),
])
def test_bad_requests(api, body, message):
    status, result = call(body)
    assert status == 400 and message in result["error"]


def test_body_that_is_not_json(api):
    response = query.handler({"body": "question=torque"}, None)
    assert response["statusCode"] == 400


def test_no_index_yet_is_503(monkeypatch):
    def missing():
        raise query.NoIndex("The manuals have not been indexed yet")

    monkeypatch.setattr(query, "get_store", missing)
    status, body = call({"question": "anything at all"})
    assert status == 503 and "indexed" in body["error"]


def test_bedrock_failure_is_502_without_internal_details(api, monkeypatch):
    def throttled(text):
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "InvokeModel")

    monkeypatch.setattr(bedrock, "embed", throttled)
    status, body = call({"question": "P-200 torque"})
    assert status == 502 and "slow down" not in body["error"]
