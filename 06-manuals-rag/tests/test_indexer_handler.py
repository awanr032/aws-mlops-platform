"""The indexer Lambda end to end, against a small in-memory imitation of S3."""

import hashlib
import io
import json
import os

import pytest

import bedrock
import indexer
import query
from conftest import fake_embed


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects = {}
        self.on_list = None  # hook to simulate an upload happening mid-build

    def put(self, key, data: bytes):
        self.objects[key] = data

    def put_object(self, Bucket, Key, Body, **kw):
        self.put(Key, Body if isinstance(Body, bytes) else Body.encode())

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def upload_file(self, filename, Bucket, Key):
        self.put(Key, open(filename, "rb").read())

    def download_file(self, Bucket, Key, filename):
        open(filename, "wb").write(self.objects[Key])

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def delete_objects(self, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)

    def get_paginator(self, name):
        fake = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                if fake.on_list:
                    fake.on_list()
                contents = [{"Key": k, "ETag": '"%s"' % hashlib.md5(v).hexdigest()}
                            for k, v in sorted(fake.objects.items()) if k.startswith(Prefix)]
                return [{"Contents": contents}]

        return Paginator()


@pytest.fixture
def s3(monkeypatch, manuals):
    fake = FakeS3()
    for key, (text, _etag) in manuals.items():
        fake.put(key, text.encode())
    monkeypatch.setattr(indexer.boto3, "client", lambda name: fake)
    monkeypatch.setattr(bedrock, "embed", fake_embed)
    monkeypatch.setenv("BUCKET", "test-bucket")
    return fake


def manifest(s3):
    return json.loads(s3.objects["index/manifest.json"])


def test_builds_index_and_writes_manifest_last(s3):
    result = indexer.handler({"Records": [{"s3": {"object": {"key": "manuals/x.md"}}}]}, None)
    m = manifest(s3)
    assert result["build_id"] == m["build_id"] and result["triggered_by"] == ["manuals/x.md"]
    assert f"index/{m['build_id']}/faiss.index" in s3.objects
    assert f"index/{m['build_id']}/chunks.json" in s3.objects
    assert len(m["manuals"]) == 3 and m["chunks"] > 20


def test_keeps_only_current_and_previous_build(s3):
    builds = []
    for _ in range(3):
        builds.append(indexer.handler({}, None)["build_id"])
    folders = {k.split("/")[1] for k in s3.objects if k.startswith("index/") and k.count("/") == 2}
    assert folders == {builds[-1], builds[-2]}


def test_new_manual_is_included_on_next_run(s3):
    indexer.handler({}, None)
    s3.put("manuals/new-fan.md", b"# F-9 Fan\n\n## 1 Belts\n\nTension the belts to 40 N.")
    indexer.handler({}, None)
    assert "manuals/new-fan.md" in manifest(s3)["manuals"]


def test_only_markdown_and_text_files_are_indexed(s3):
    s3.put("manuals/photo.jpg", b"\xff\xd8")
    indexer.handler({}, None)
    assert "manuals/photo.jpg" not in manifest(s3)["manuals"]


def test_run_superseded_by_upload_during_build_does_not_publish(s3):
    indexer.handler({}, None)
    first = manifest(s3)["build_id"]
    calls = {"n": 0}

    def upload_mid_build():  # listing 1 reads the manuals; listing 2 is the check before publishing
        calls["n"] += 1
        if calls["n"] == 2:
            s3.put("manuals/late.md", b"# Late\n\n## 1 Note\n\nArrived during the build.")

    s3.on_list = upload_mid_build
    result = indexer.handler({}, None)
    assert "superseded" in result
    assert manifest(s3)["build_id"] == first  # the older index stays published


def test_removing_every_manual_removes_the_index(s3):
    indexer.handler({}, None)
    for key in [k for k in s3.objects if k.startswith("manuals/")]:
        s3.delete_object("b", key)
    assert indexer.handler({}, None) == {"chunks": 0}
    assert "index/manifest.json" not in s3.objects


def test_question_lambda_loads_what_the_indexer_wrote(s3, monkeypatch, tmp_path):
    indexer.handler({}, None)
    monkeypatch.setattr(query, "_s3", s3)
    monkeypatch.setattr(query, "_cache", {"store": None, "manifest": None, "checked": 0.0})
    store, m = query.get_store()
    assert m["build_id"] == manifest(s3)["build_id"] and len(store.chunks) == m["chunks"]
    # within REFRESH_SECONDS the cached index is reused without touching S3
    s3.objects.clear()
    assert query.get_store()[0] is store


def test_question_lambda_refuses_index_from_another_embedding_model(s3, monkeypatch):
    indexer.handler({}, None)
    m = manifest(s3)
    m["embedding_model"] = "some.other-model"
    s3.put("index/manifest.json", json.dumps(m).encode())
    monkeypatch.setattr(query, "_s3", s3)
    monkeypatch.setattr(query, "_cache", {"store": None, "manifest": None, "checked": 0.0})
    with pytest.raises(query.NoIndex, match="re-index"):
        query.get_store()
