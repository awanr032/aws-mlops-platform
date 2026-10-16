"""Work-order rules: input validation, status transitions and storage."""

from __future__ import annotations

PRIORITIES = {"low", "medium", "high", "critical"}
STATUSES = {"open", "in_progress", "closed"}

# Which status changes are allowed. A closed work order cannot be reopened.
TRANSITIONS = {
    "open": {"in_progress", "closed"},
    "in_progress": {"closed"},
    "closed": set(),
}

MAX_ASSET_ID = 64
MAX_DESCRIPTION = 1000
UPDATABLE_FIELDS = {"status", "priority", "description"}


class ValidationError(Exception):
    """Raised when a request body breaks the rules; becomes an HTTP 400."""


def _text(payload: dict, field: str, max_len: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"'{field}' is required and must be a non-empty string")
    value = value.strip()
    if len(value) > max_len:
        raise ValidationError(f"'{field}' must be at most {max_len} characters")
    return value


def _priority(value) -> str:
    if value not in PRIORITIES:
        raise ValidationError(f"'priority' must be one of {sorted(PRIORITIES)}")
    return value


def validate_new(payload) -> dict:
    """Check the body of a POST /work-orders request and return the cleaned fields."""
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    unknown = set(payload) - {"asset_id", "description", "priority"}
    if unknown:
        raise ValidationError(f"Unknown fields: {sorted(unknown)}")
    return {
        "asset_id": _text(payload, "asset_id", MAX_ASSET_ID),
        "description": _text(payload, "description", MAX_DESCRIPTION),
        "priority": _priority(payload.get("priority", "medium")),
    }


def validate_update(payload, current: dict) -> dict:
    """Check the body of a PATCH request against the current work order."""
    if not isinstance(payload, dict) or not payload:
        raise ValidationError("Request body must be a non-empty JSON object")
    unknown = set(payload) - UPDATABLE_FIELDS
    if unknown:
        raise ValidationError(
            f"Only {sorted(UPDATABLE_FIELDS)} can be updated; got {sorted(unknown)}"
        )

    changes = {}
    if "description" in payload:
        changes["description"] = _text(payload, "description", MAX_DESCRIPTION)
    if "priority" in payload:
        changes["priority"] = _priority(payload["priority"])
    if "status" in payload:
        new_status = payload["status"]
        if new_status not in STATUSES:
            raise ValidationError(f"'status' must be one of {sorted(STATUSES)}")
        old_status = current["status"]
        if new_status != old_status and new_status not in TRANSITIONS[old_status]:
            raise ValidationError(f"Cannot change status from '{old_status}' to '{new_status}'")
        changes["status"] = new_status

    if current["status"] == "closed" and changes:
        raise ValidationError("Closed work orders cannot be changed")
    return changes


def new_work_order(fields: dict, work_order_id: str, now: str) -> dict:
    return {
        "work_order_id": work_order_id,
        **fields,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }


class DynamoRepository:
    """Stores work orders in a DynamoDB table."""

    ASSET_INDEX = "asset_id-created_at-index"

    def __init__(self, table):
        self.table = table

    def put(self, item: dict) -> None:
        self.table.put_item(
            Item=item, ConditionExpression="attribute_not_exists(work_order_id)"
        )

    def get(self, work_order_id: str):
        return self.table.get_item(Key={"work_order_id": work_order_id}).get("Item")

    def list_by_asset(self, asset_id: str, limit: int = 50) -> list:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            IndexName=self.ASSET_INDEX,
            KeyConditionExpression=Key("asset_id").eq(asset_id),
            ScanIndexForward=False,  # newest first
            Limit=limit,
        )
        return response.get("Items", [])

    def update(self, work_order_id: str, changes: dict, now: str) -> dict:
        fields = {**changes, "updated_at": now}
        names = {f"#{k}": k for k in fields}
        values = {f":{k}": v for k, v in fields.items()}
        expression = "SET " + ", ".join(f"#{k} = :{k}" for k in fields)
        response = self.table.update_item(
            Key={"work_order_id": work_order_id},
            UpdateExpression=expression,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(work_order_id)",
            ReturnValues="ALL_NEW",
        )
        return response["Attributes"]
