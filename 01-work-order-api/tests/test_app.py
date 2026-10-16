"""Tests for the API handler. They use an in-memory store, so no AWS account is needed."""

import json

import pytest

from app import handler


class InMemoryRepository:
    def __init__(self):
        self.items = {}

    def put(self, item):
        self.items[item["work_order_id"]] = dict(item)

    def get(self, work_order_id):
        item = self.items.get(work_order_id)
        return dict(item) if item else None

    def list_by_asset(self, asset_id, limit=50):
        matches = [i for i in self.items.values() if i["asset_id"] == asset_id]
        return sorted(matches, key=lambda i: i["created_at"], reverse=True)[:limit]

    def update(self, work_order_id, changes, now):
        self.items[work_order_id].update(changes, updated_at=now)
        return dict(self.items[work_order_id])


@pytest.fixture
def repo():
    return InMemoryRepository()


def call(repo, method, resource, body=None, path_id=None, query=None):
    event = {
        "httpMethod": method,
        "resource": resource,
        "body": json.dumps(body) if isinstance(body, (dict, list)) else body,
        "pathParameters": {"id": path_id} if path_id else None,
        "queryStringParameters": query,
    }
    response = handler(event, None, repository=repo)
    return response["statusCode"], json.loads(response["body"])


def create(repo, **overrides):
    body = {"asset_id": "P-101", "description": "Leaking seal", "priority": "high"}
    body.update(overrides)
    return call(repo, "POST", "/work-orders", body)


# --- creating -------------------------------------------------------------

def test_create_returns_201_with_id_and_open_status(repo):
    status, body = create(repo)
    assert status == 201
    assert body["work_order_id"]
    assert body["status"] == "open"
    assert body["asset_id"] == "P-101"


def test_priority_defaults_to_medium(repo):
    status, body = call(
        repo, "POST", "/work-orders", {"asset_id": "P-101", "description": "Check"}
    )
    assert status == 201
    assert body["priority"] == "medium"


@pytest.mark.parametrize(
    "body, message",
    [
        ({"description": "No asset"}, "asset_id"),
        ({"asset_id": "P-101"}, "description"),
        ({"asset_id": "  ", "description": "Blank asset"}, "asset_id"),
        ({"asset_id": "P-101", "description": "x", "priority": "urgent"}, "priority"),
        ({"asset_id": "P-101", "description": "x", "colour": "red"}, "Unknown fields"),
        ({"asset_id": "P" * 65, "description": "x"}, "at most 64"),
        (["not", "an", "object"], "JSON object"),
    ],
)
def test_create_rejects_bad_input(repo, body, message):
    status, response = call(repo, "POST", "/work-orders", body)
    assert status == 400
    assert message in response["error"]


def test_create_rejects_invalid_json(repo):
    status, response = call(repo, "POST", "/work-orders", "{not json")
    assert status == 400
    assert "not valid JSON" in response["error"]


# --- reading --------------------------------------------------------------

def test_get_existing_work_order(repo):
    _, created = create(repo)
    status, body = call(repo, "GET", "/work-orders/{id}", path_id=created["work_order_id"])
    assert status == 200
    assert body == created


def test_get_missing_work_order_returns_404(repo):
    status, body = call(repo, "GET", "/work-orders/{id}", path_id="does-not-exist")
    assert status == 404


def test_list_by_asset_only_returns_that_asset(repo):
    create(repo, asset_id="P-101")
    create(repo, asset_id="P-101")
    create(repo, asset_id="C-7")
    status, body = call(repo, "GET", "/work-orders", query={"asset_id": "P-101"})
    assert status == 200
    assert len(body["items"]) == 2
    assert {i["asset_id"] for i in body["items"]} == {"P-101"}


def test_list_requires_asset_id(repo):
    status, body = call(repo, "GET", "/work-orders")
    assert status == 400


# --- updating -------------------------------------------------------------

def test_status_moves_open_to_in_progress_to_closed(repo):
    _, created = create(repo)
    wo_id = created["work_order_id"]
    status, body = call(repo, "PATCH", "/work-orders/{id}", {"status": "in_progress"}, wo_id)
    assert status == 200 and body["status"] == "in_progress"
    status, body = call(repo, "PATCH", "/work-orders/{id}", {"status": "closed"}, wo_id)
    assert status == 200 and body["status"] == "closed"


def test_closed_work_order_cannot_be_reopened(repo):
    _, created = create(repo)
    wo_id = created["work_order_id"]
    call(repo, "PATCH", "/work-orders/{id}", {"status": "closed"}, wo_id)
    status, body = call(repo, "PATCH", "/work-orders/{id}", {"status": "open"}, wo_id)
    assert status == 400
    assert "Cannot change status" in body["error"]


def test_closed_work_order_cannot_be_edited(repo):
    _, created = create(repo)
    wo_id = created["work_order_id"]
    call(repo, "PATCH", "/work-orders/{id}", {"status": "closed"}, wo_id)
    status, body = call(repo, "PATCH", "/work-orders/{id}", {"priority": "low"}, wo_id)
    assert status == 400


def test_in_progress_cannot_go_back_to_open(repo):
    _, created = create(repo)
    wo_id = created["work_order_id"]
    call(repo, "PATCH", "/work-orders/{id}", {"status": "in_progress"}, wo_id)
    status, _ = call(repo, "PATCH", "/work-orders/{id}", {"status": "open"}, wo_id)
    assert status == 400


def test_update_rejects_fields_that_cannot_change(repo):
    _, created = create(repo)
    status, body = call(
        repo, "PATCH", "/work-orders/{id}", {"asset_id": "X-1"}, created["work_order_id"]
    )
    assert status == 400
    assert "can be updated" in body["error"]


def test_update_missing_work_order_returns_404(repo):
    status, _ = call(repo, "PATCH", "/work-orders/{id}", {"status": "closed"}, "nope")
    assert status == 404


# --- other ----------------------------------------------------------------

def test_unsupported_method_returns_405(repo):
    status, _ = call(repo, "DELETE", "/work-orders")
    assert status == 405


def test_unexpected_error_returns_500_without_details(repo):
    class BrokenRepository(InMemoryRepository):
        def put(self, item):
            raise RuntimeError("database is on fire")

    status, body = create(BrokenRepository())
    assert status == 500
    assert "fire" not in body["error"]
