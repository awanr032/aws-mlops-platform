"""Lambda entry point: reads S3 "file arrived" messages from SQS and processes each CSV."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import Counter
from datetime import date, datetime, timezone
from urllib.parse import unquote_plus

from validate import FileRejected, to_csv, validate_csv

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_BYTES = 5 * 1024 * 1024  # 5 MB

_clients = {}


def _client(name):
    if name not in _clients:
        import boto3

        _clients[name] = boto3.client(name)
    return _clients[name]


def _error_code(exc) -> str:
    return getattr(exc, "response", {}).get("Error", {}).get("Code", "")


def _exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:  # botocore ClientError
        if _error_code(exc) in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _put_text(s3, bucket: str, key: str, text: str, content_type: str = "text/csv") -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"), ContentType=content_type)


def _summary(name: str, accepted: int, rejected: int, reasons: Counter, file_error: str = "") -> str:
    lines = [f"File: {name}"]
    if file_error:
        lines.append(f"Whole file rejected: {file_error}")
    else:
        lines.append(f"Rows accepted: {accepted}")
        lines.append(f"Rows rejected: {rejected}")
        if reasons:
            lines.append("")
            lines.append("Most common problems:")
            lines.extend(f"  {count} x {reason}" for reason, count in reasons.most_common(5))
    return "\n".join(lines)


def process_object(s3, sns, bucket: str, key: str, etag: str, topic_arn: str, today: date) -> str:
    """Validate one uploaded CSV. Returns 'processed' or 'skipped'.

    Idempotent: a marker object records each (key, version) that has been handled, so a
    repeated message (SQS can deliver twice) does not produce a second email.
    """
    if not key.startswith("incoming/"):
        logger.info(json.dumps({"skip": "outside incoming/", "key": key}))
        return "skipped"

    name = key[len("incoming/"):]
    fingerprint = hashlib.sha256(f"{key}|{etag}".encode()).hexdigest()
    marker = f"_state/{fingerprint}.done"
    if _exists(s3, bucket, marker):
        logger.info(json.dumps({"skip": "already processed", "key": key}))
        return "skipped"

    obj = s3.get_object(Bucket=bucket, Key=key)
    file_error = ""
    accepted = rejected = 0
    reasons: Counter = Counter()

    if obj.get("ContentLength", 0) > MAX_BYTES:
        file_error = f"file is larger than {MAX_BYTES // (1024 * 1024)} MB"
    else:
        # A file that is not UTF-8 text raises here on purpose: the message is retried,
        # then lands in the dead-letter queue for a human to inspect.
        text = obj["Body"].read().decode("utf-8")
        try:
            result = validate_csv(text, today)
        except FileRejected as exc:
            file_error = str(exc)
        else:
            accepted, rejected = len(result.accepted), len(result.rejected)
            if result.accepted:
                _put_text(s3, bucket, f"processed/{name}", to_csv(result.accepted, result.columns))
            if result.rejected:
                columns = ["row_number", "error"] + result.columns
                _put_text(s3, bucket, f"rejected/{name}", to_csv(result.rejected, columns))
                for row in result.rejected:
                    for reason in row["error"].split("; "):
                        # Group "date '31/02' ..." and "date '1/1' ..." as one kind of problem
                        reasons[re.sub(r"'[^']*'", "'...'", reason)] += 1

    if file_error:
        _put_text(s3, bucket, f"rejected/{name}.error.txt", file_error + "\n", "text/plain")

    # Claim the marker only once. If another copy of this message got here first,
    # S3 refuses the write and we stay quiet instead of sending a duplicate email.
    stamp = json.dumps({"key": key, "etag": etag, "at": datetime.now(timezone.utc).isoformat()})
    try:
        s3.put_object(Bucket=bucket, Key=marker, Body=stamp.encode(), IfNoneMatch="*")
    except Exception as exc:
        if _error_code(exc) in ("PreconditionFailed", "ConditionalRequestConflict"):
            logger.info(json.dumps({"skip": "processed concurrently", "key": key}))
            return "skipped"
        raise

    message = _summary(name, accepted, rejected, reasons, file_error)
    logger.info(json.dumps({"key": key, "accepted": accepted, "rejected": rejected, "file_error": file_error}))
    if topic_arn:
        status = "file rejected" if file_error else f"{accepted} accepted, {rejected} rejected"
        subject = f"Ingest: {name} - {status}"[:100]  # SNS subject limit
        sns.publish(TopicArn=topic_arn, Subject=subject, Message=message)
    return "processed"


def handler(event, context, s3=None, sns=None, today=None):
    """SQS batch handler. Failed messages are reported individually so only they are retried."""
    s3 = s3 or _client("s3")
    sns = sns or _client("sns")
    today = today or datetime.now(timezone.utc).date()
    topic_arn = os.environ.get("TOPIC_ARN", "")

    failures = []
    for message in event.get("Records", []):
        try:
            body = json.loads(message["body"])
            if body.get("Event") == "s3:TestEvent":
                continue  # S3 sends this once when the notification is first set up
            for record in body.get("Records", []):
                obj = record["s3"]["object"]
                process_object(
                    s3,
                    sns,
                    bucket=record["s3"]["bucket"]["name"],
                    key=unquote_plus(obj["key"]),
                    etag=obj.get("eTag", ""),
                    topic_arn=topic_arn,
                    today=today,
                )
        except Exception:
            logger.exception("Failed to process message %s", message.get("messageId"))
            failures.append({"itemIdentifier": message["messageId"]})

    return {"batchItemFailures": failures}
