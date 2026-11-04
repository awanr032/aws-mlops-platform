"""Question Lambda behind API Gateway: POST /ask {"question": "..."}.

question → embed (Bedrock) → nearest chunks (FAISS) → answer from those chunks only (Bedrock)
→ check citations → answer + sources.

The index is loaded once per container and re-checked at most every REFRESH_SECONDS, so a
re-index is picked up within a minute without paying an S3 download on every request.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

import bedrock
import prompts
from indexer import INDEX_PREFIX, MANIFEST_KEY
from store import CHUNKS_FILE, INDEX_FILE, VectorStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TOP_K = int(os.environ.get("TOP_K", "4"))
MAX_TOP_K = 8
MAX_QUESTION_CHARS = 500
REFRESH_SECONDS = 60

_cache = {"store": None, "manifest": None, "checked": 0.0}
_s3 = None
_cold = True


class BadRequest(Exception):
    pass


class NoIndex(Exception):
    pass


def parse_request(event: dict) -> tuple[str, int, bool]:
    """Accepts an API Gateway proxy event, or a direct invoke {"question": ...}."""
    if "body" in event:
        raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raise BadRequest("Body must be JSON, e.g. {\"question\": \"...\"}") from None
    else:
        body = event
    if not isinstance(body, dict):
        raise BadRequest("Body must be a JSON object")

    question = body.get("question")
    if not isinstance(question, str) or len(question.strip()) < 3:
        raise BadRequest("'question' is required (at least 3 characters)")
    if len(question) > MAX_QUESTION_CHARS:
        raise BadRequest(f"'question' must be at most {MAX_QUESTION_CHARS} characters")
    top_k = body.get("top_k", TOP_K)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= MAX_TOP_K:
        raise BadRequest(f"'top_k' must be a whole number from 1 to {MAX_TOP_K}")
    retrieve_only = body.get("retrieve_only", False)
    if not isinstance(retrieve_only, bool):
        raise BadRequest("'retrieve_only' must be true or false")
    return question.strip(), top_k, retrieve_only


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def get_store() -> tuple[VectorStore, dict]:
    now = time.time()
    if _cache["store"] is not None and now - _cache["checked"] < REFRESH_SECONDS:
        return _cache["store"], _cache["manifest"]
    s3, bucket = _s3_client(), os.environ["BUCKET"]
    try:
        manifest = json.loads(s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read())
    except s3.exceptions.NoSuchKey:
        raise NoIndex("The manuals have not been indexed yet") from None
    if manifest["embedding_model"] != bedrock.EMBED_MODEL_ID:
        raise NoIndex(f"Index was built with {manifest['embedding_model']}; re-index with "
                      f"{bedrock.EMBED_MODEL_ID}")
    if _cache["manifest"] is None or manifest["build_id"] != _cache["manifest"]["build_id"]:
        folder = f"/tmp/index-{manifest['build_id']}"
        os.makedirs(folder, exist_ok=True)
        for name in (INDEX_FILE, CHUNKS_FILE):
            s3.download_file(bucket, f"{INDEX_PREFIX}{manifest['build_id']}/{name}", f"{folder}/{name}")
        _cache["store"] = VectorStore.load(folder)
        _cache["manifest"] = manifest
        logger.info(json.dumps({"event": "index_loaded", "build_id": manifest["build_id"],
                                "chunks": manifest["chunks"]}))
    _cache["checked"] = now
    return _cache["store"], _cache["manifest"]


def respond(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 1)


def handler(event, context):
    global _cold
    cold, _cold = _cold, False
    started = time.perf_counter()
    try:
        question, top_k, retrieve_only = parse_request(event)
    except BadRequest as exc:
        return respond(400, {"error": str(exc)})

    try:
        t = time.perf_counter()
        store, manifest = get_store()
        load_ms = _ms(t)

        t = time.perf_counter()
        vector = bedrock.embed(question)
        embed_ms = _ms(t)

        t = time.perf_counter()
        hits = store.search(vector, top_k)
        search_ms = _ms(t)
        sources = [prompts.source_entry(n, chunk, score) for n, (chunk, score) in enumerate(hits, start=1)]

        result, generate_ms = {}, 0.0
        if not retrieve_only:
            t = time.perf_counter()
            raw = bedrock.generate(prompts.SYSTEM_PROMPT, prompts.build_user_message(question, hits))
            generate_ms = _ms(t)
            result = prompts.parse_answer(raw, hits)
    except NoIndex as exc:
        return respond(503, {"error": str(exc)})
    except ClientError as exc:
        logger.error(json.dumps({"event": "bedrock_or_s3_error", "code": exc.response["Error"]["Code"],
                                 "message": exc.response["Error"]["Message"]}))
        return respond(502, {"error": "A backend service failed; please try again shortly."})

    timings = {"index_load": load_ms, "embed": embed_ms, "search": search_ms,
               "generate": generate_ms, "total": _ms(started)}
    logger.info(json.dumps({"event": "ask", "retrieve_only": retrieve_only, "found": result.get("found"),
                            "citations": len(result.get("citations", [])),
                            "top_score": sources[0]["score"] if sources else None,
                            "cold_start": cold, "ms": timings}))
    return respond(200, {
        "question": question,
        **result,
        "sources": sources,
        "index": {"build_id": manifest["build_id"], "chunks": manifest["chunks"]},
        "models": {"embedding": bedrock.EMBED_MODEL_ID,
                   **({} if retrieve_only else {"answer": bedrock.CHAT_MODEL_ID})},
        "cold_start": cold,
        "timings_ms": timings,
    })
