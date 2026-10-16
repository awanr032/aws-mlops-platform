"""Checks that the DynamoDB repository sends the right requests to the table."""

from workorders import DynamoRepository


class FakeTable:
    def __init__(self):
        self.calls = []

    def put_item(self, **kwargs):
        self.calls.append(("put_item", kwargs))

    def update_item(self, **kwargs):
        self.calls.append(("update_item", kwargs))
        return {"Attributes": {"work_order_id": kwargs["Key"]["work_order_id"]}}


def test_put_refuses_to_overwrite_existing_item():
    table = FakeTable()
    DynamoRepository(table).put({"work_order_id": "a1"})
    _, kwargs = table.calls[0]
    assert kwargs["ConditionExpression"] == "attribute_not_exists(work_order_id)"


def test_update_builds_expression_and_only_updates_existing_items():
    table = FakeTable()
    DynamoRepository(table).update("a1", {"status": "closed"}, "2026-10-16T10:00:00+00:00")
    _, kwargs = table.calls[0]
    assert kwargs["UpdateExpression"] == "SET #status = :status, #updated_at = :updated_at"
    assert kwargs["ExpressionAttributeNames"]["#status"] == "status"
    assert kwargs["ExpressionAttributeValues"][":status"] == "closed"
    assert kwargs["ConditionExpression"] == "attribute_exists(work_order_id)"
