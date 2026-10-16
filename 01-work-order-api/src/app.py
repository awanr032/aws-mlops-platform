"""Lambda entry point: turns API Gateway requests into work-order operations."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from workorders import (
    DynamoRepository,
    ValidationError,
    new_work_order,
    validate_new,
    validate_update,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_repository = None


def _default_repository() -> DynamoRepository:
    """Created once per Lambda container and reused across requests."""
    global _repository
    if _repository is None:
        import boto3

        table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
        _repository = DynamoRepository(table)
    return _repository


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _error(status: int, message: str) -> dict:
    return _response(status, {"error": message})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_body(event: dict):
    raw = event.get("body")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise ValidationError("Request body is not valid JSON")


def handler(event, context, repository=None):
    repo = repository or _default_repository()
    method = event.get("httpMethod")
    resource = event.get("resource")
    path_params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}

    logger.info(json.dumps({"method": method, "resource": resource}))

    try:
        if resource == "/work-orders" and method == "POST":
            fields = validate_new(_parse_body(event))
            item = new_work_order(fields, str(uuid.uuid4()), _now())
            repo.put(item)
            return _response(201, item)

        if resource == "/work-orders" and method == "GET":
            asset_id = query.get("asset_id")
            if not asset_id:
                return _error(400, "Query parameter 'asset_id' is required")
            return _response(200, {"items": repo.list_by_asset(asset_id)})

        if resource == "/work-orders/{id}":
            work_order_id = path_params.get("id", "")
            current = repo.get(work_order_id)
            if current is None:
                return _error(404, f"Work order '{work_order_id}' not found")

            if method == "GET":
                return _response(200, current)

            if method == "PATCH":
                changes = validate_update(_parse_body(event), current)
                if not changes:
                    return _response(200, current)
                return _response(200, repo.update(work_order_id, changes, _now()))

        return _error(405, f"{method} {resource} is not supported")

    except ValidationError as exc:
        return _error(400, str(exc))
    except Exception:
        logger.exception("Unhandled error")
        return _error(500, "Internal server error")
