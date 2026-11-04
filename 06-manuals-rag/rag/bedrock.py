"""The two Bedrock calls: turn text into an embedding, and generate an answer."""

from __future__ import annotations

import json
import os

import boto3
from botocore.config import Config

EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "mistral.ministral-3-14b-instruct")
EMBED_DIMENSIONS = int(os.environ.get("EMBED_DIMENSIONS", "1024"))

_client = None


def client():
    global _client
    if _client is None:
        # "adaptive" retries back off automatically when Bedrock throttles us.
        _client = boto3.client("bedrock-runtime",
                               config=Config(retries={"mode": "adaptive", "max_attempts": 8}))
    return _client


def embed(text: str) -> list[float]:
    """Titan Text Embeddings V2: text in, EMBED_DIMENSIONS numbers out (already normalised)."""
    body = {"inputText": text, "dimensions": EMBED_DIMENSIONS, "normalize": True}
    response = client().invoke_model(modelId=EMBED_MODEL_ID, body=json.dumps(body),
                                     contentType="application/json", accept="application/json")
    return json.loads(response["body"].read())["embedding"]


def generate(system: str, user: str, max_tokens: int = 500) -> str:
    response = client().converse(
        modelId=CHAT_MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"temperature": 0, "maxTokens": max_tokens},
    )
    return "".join(part.get("text", "") for part in response["output"]["message"]["content"])
