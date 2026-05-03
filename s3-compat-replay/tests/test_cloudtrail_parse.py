from __future__ import annotations

from s3_compat_replay.cloudtrail_parse import parse_cloudtrail

from conftest import make_event, write_gz, write_jsonl, write_records


def test_parses_cloudtrail_json_with_records(tmp_path):
    path = write_records(tmp_path / "events.json", [make_event("GetObject")])
    events, warnings = parse_cloudtrail(path)
    assert warnings == []
    assert len(events) == 1
    assert events[0].eventName == "GetObject"


def test_parses_cloudtrail_json_gz(tmp_path):
    path = write_gz(tmp_path / "events.json.gz", [make_event("HeadObject")])
    events, _ = parse_cloudtrail(path)
    assert len(events) == 1
    assert events[0].eventName == "HeadObject"


def test_parses_json_lines(tmp_path):
    path = write_jsonl(tmp_path / "events.jsonl", [make_event("PutObject"), make_event("DeleteObject")])
    events, _ = parse_cloudtrail(path)
    assert [event.eventName for event in events] == ["PutObject", "DeleteObject"]


def test_extracts_event_fields(tmp_path):
    event = make_event("GetObject", additionalEventData={"SignatureVersion": "SigV4"}, responseElements={"x": "y"})
    path = write_records(tmp_path / "events.json", [event])
    parsed, _ = parse_cloudtrail(path)
    first = parsed[0]
    assert first.eventName == "GetObject"
    assert first.requestParameters["bucketName"] == "source-bucket-example"
    assert first.requestParameters["key"].endswith(".pdf")
    assert first.responseElements == {"x": "y"}
    assert first.additionalEventData == {"SignatureVersion": "SigV4"}


def test_directory_mixed_inputs(tmp_path):
    write_records(tmp_path / "a.json", [make_event("GetObject")])
    write_jsonl(tmp_path / "b.jsonl", [make_event("HeadObject")])
    events, _ = parse_cloudtrail(tmp_path)
    assert sorted(event.eventName for event in events) == ["GetObject", "HeadObject"]
