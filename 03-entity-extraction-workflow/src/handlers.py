"""The three Lambda functions used by the Step Functions workflow.

validate_input  -> checks the work order before anything is spent on the model
extract         -> asks the Bedrock model to extract entities
check_output    -> parses and checks the model's answer
"""

from __future__ import annotations

import json
import logging
import os

from extraction import (  # noqa: F401  (InvalidInput is raised from clean_input)
    SYSTEM_PROMPT,
    InvalidInput,
    build_messages,
    check_entities,
    clean_input,
    parse_model_output,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Bedrock errors worth retrying: the service is busy or briefly unavailable.
RETRYABLE = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "InternalServerException",
}


class ModelBusy(Exception):
    """Temporary Bedrock problem. Step Functions retries this with backoff."""


class ModelCallFailed(Exception):
    """Permanent Bedrock problem (permissions, bad model ID). Not retried."""


_bedrock = None


def _bedrock_client():
    global _bedrock
    if _bedrock is None:
        import boto3

        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


def validate_input(event, context):
    """Event shape: {"input": <the workflow input>, "execution_name": "..."}.

    Raises InvalidInput, which the workflow catches by name.
    """
    cleaned = clean_input(event.get("input"))
    # Fall back to the Step Functions execution name so every result has an ID.
    if not cleaned["work_order_id"]:
        cleaned["work_order_id"] = event.get("execution_name") or "unknown"
    logger.info(json.dumps({"step": "validate", "work_order_id": cleaned["work_order_id"]}))
    return cleaned


def extract(event, context, client=None):
    client = client or _bedrock_client()
    model_id = os.environ["MODEL_ID"]
    try:
        response = client.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=build_messages(event["text"]),
            inferenceConfig={"maxTokens": 300, "temperature": 0},
        )
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in RETRYABLE:
            raise ModelBusy(f"{code}: {exc}") from exc
        raise ModelCallFailed(f"{code or type(exc).__name__}: {exc}") from exc

    blocks = response["output"]["message"]["content"]
    raw = "".join(block.get("text", "") for block in blocks)
    usage = response.get("usage", {})
    logger.info(json.dumps({
        "step": "extract",
        "model_id": model_id,
        "input_tokens": usage.get("inputTokens"),
        "output_tokens": usage.get("outputTokens"),
        "latency_ms": response.get("metrics", {}).get("latencyMs"),
    }))
    return {
        "raw": raw,
        "model_id": model_id,
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
    }


def check_output(event, context):
    data, problem = parse_model_output(event.get("raw", ""))
    if problem:
        result = {"valid": False, "entities": {}, "problems": [problem]}
    else:
        entities, problems = check_entities(data, event.get("text", ""))
        result = {"valid": not problems, "entities": entities, "problems": problems}
    logger.info(json.dumps({"step": "check", "valid": result["valid"], "problems": result["problems"]}))
    return result
