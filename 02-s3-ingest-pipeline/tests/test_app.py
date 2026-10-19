"""Handler tests with in-memory stand-ins for S3 and SNS; no AWS account needed."""

import io
import json
from datetime import date

import pytest
from botocore.exceptions import ClientError

import app

TODAY = date(2026, 10, 19)
BUCKET = "ingest-bucket"
TOPIC = "arn:aws:sns:eu-west-2:123456789012:ingest"


class FakeS3:
    def __init__(self):
        self.objects = {}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def get_object(self, Bucket, Key):
        data = self.objects[Key]
        return {"Body": io.BytesIO(data), "ContentLength": len(data)}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):
        if IfNoneMatch == "*" and Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Key] = Body

    def text(self, key):
        return self.objects[key].decode("utf-8")


class FakeSNS:
    def __init__(self):
        self.messages = []

    def publish(self, TopicArn, Subject, Message):
        self.messages.append({"subject": Subject, "message": Message})


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TOPIC_ARN", TOPIC)
    return FakeS3(), FakeSNS()


def sqs_event(*keys, message_id="m1", etag="abc"):
    body = {
        "Records": [
            {"s3": {"bucket": {"name": BUCKET}, "object": {"key": k, "eTag": etag}}} for k in keys
        ]
    }
    return {"Records": [{"messageId": message_id, "body": json.dumps(body)}]}


def run(event, s3, sns):
    return app.handler(event, None, s3=s3, sns=sns, today=TODAY)


MIXED = (
    "asset_id,date,priority,description\n"
    "P-101,2026-10-01,high,Leaking seal\n"
    "P-102,2026-10-02,low,Routine check\n"
    ",2026-10-03,medium,Noisy bearing\n"
).encode()


def test_good_and_bad_rows_are_split_and_summarised(env):
    s3, sns = env
    s3.objects["incoming/pumps.csv"] = MIXED

    assert run(sqs_event("incoming/pumps.csv"), s3, sns) == {"batchItemFailures": []}

    assert s3.text("processed/pumps.csv").count("\n") == 3  # header + 2 rows
    assert "missing asset_id" in s3.text("rejected/pumps.csv")
    assert sns.messages[0]["subject"] == "Ingest: pumps.csv - 2 accepted, 1 rejected"
    assert "1 x missing asset_id" in sns.messages[0]["message"]


def test_same_message_twice_sends_one_email(env):
    s3, sns = env
    s3.objects["incoming/pumps.csv"] = MIXED
    run(sqs_event("incoming/pumps.csv"), s3, sns)
    run(sqs_event("incoming/pumps.csv"), s3, sns)
    assert len(sns.messages) == 1


def test_new_version_of_same_file_is_processed_again(env):
    s3, sns = env
    s3.objects["incoming/pumps.csv"] = MIXED
    run(sqs_event("incoming/pumps.csv", etag="v1"), s3, sns)
    run(sqs_event("incoming/pumps.csv", etag="v2"), s3, sns)
    assert len(sns.messages) == 2


def test_file_with_wrong_columns_is_rejected_whole(env):
    s3, sns = env
    s3.objects["incoming/bad.csv"] = b"name,value\nx,1\n"
    run(sqs_event("incoming/bad.csv"), s3, sns)
    assert "missing required columns" in s3.text("rejected/bad.csv.error.txt")
    assert "file rejected" in sns.messages[0]["subject"]
    assert "processed/bad.csv" not in s3.objects


def test_unreadable_file_fails_the_message_so_it_is_retried(env):
    s3, sns = env
    s3.objects["incoming/poison.csv"] = "asset_id\ncafé".encode("latin-1")
    result = run(sqs_event("incoming/poison.csv", message_id="poison"), s3, sns)
    assert result == {"batchItemFailures": [{"itemIdentifier": "poison"}]}
    assert not sns.messages


def test_one_bad_message_does_not_fail_the_others(env):
    s3, sns = env
    s3.objects["incoming/good.csv"] = MIXED
    s3.objects["incoming/poison.csv"] = b"\xff\xfe\x00"
    event = {
        "Records": sqs_event("incoming/good.csv", message_id="ok")["Records"]
        + sqs_event("incoming/poison.csv", message_id="bad")["Records"]
    }
    result = run(event, s3, sns)
    assert result == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert "processed/good.csv" in s3.objects


def test_s3_test_event_is_ignored(env):
    s3, sns = env
    event = {"Records": [{"messageId": "t", "body": json.dumps({"Event": "s3:TestEvent"})}]}
    assert run(event, s3, sns) == {"batchItemFailures": []}


def test_file_names_with_spaces_are_decoded(env):
    s3, sns = env
    s3.objects["incoming/october pumps.csv"] = MIXED
    run(sqs_event("incoming/october+pumps.csv"), s3, sns)  # S3 encodes spaces as +
    assert "processed/october pumps.csv" in s3.objects


def test_oversized_file_is_rejected_without_reading(env, monkeypatch):
    s3, sns = env
    monkeypatch.setattr(app, "MAX_BYTES", 10)
    s3.objects["incoming/big.csv"] = MIXED
    run(sqs_event("incoming/big.csv"), s3, sns)
    assert "larger than" in s3.text("rejected/big.csv.error.txt")
