"""Valhalla client: replay never touches the network; record writes a cassette replay can read.

The live server here is a stdlib HTTP stub on 127.0.0.1, not Valhalla."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from conftest import CASSETTES, ISO_FIXTURE
from spine.compute.valhalla_client import (
    CassetteMissing,
    ValhallaClient,
    cassette_path,
    matrix_request,
    parse_matrix_minutes,
    request_key,
)

ISO_BODY = {"locations": [{"lat": 37.35, "lon": -121.95}], "costing": "auto", "contours": [{"time": 15}]}


@pytest.fixture()
def stub_server() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    seen: list[dict[str, Any]] = []
    iso = json.loads(ISO_FIXTURE.read_text())

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"path": self.path, "body": body})
            out = json.dumps({"type": iso["type"], "features": iso["features"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args: Any) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", seen
    srv.shutdown()


def test_request_key_is_canonical() -> None:
    a = {"b": 1, "a": [1, 2]}
    assert request_key("isochrone", a) == request_key("isochrone", {"a": [1, 2], "b": 1})
    assert request_key("isochrone", a) != request_key("sources_to_targets", a)


def test_replay_without_cassette_raises(tmp_path: Path) -> None:
    with pytest.raises(CassetteMissing):
        ValhallaClient(mode="replay", cassette_dir=tmp_path).isochrone(ISO_BODY)


def test_record_then_replay_round_trip(tmp_path: Path, stub_server: tuple[str, list[dict[str, Any]]]) -> None:
    url, seen = stub_server
    live = ValhallaClient(base_url=url, mode="record", cassette_dir=tmp_path, note="stub recording")
    first = live.isochrone(ISO_BODY)
    assert seen == [{"path": "/isochrone", "body": ISO_BODY}]
    doc = json.loads(cassette_path(tmp_path, "isochrone", ISO_BODY).read_text())
    assert doc["request"] == ISO_BODY and doc["_note"] == "stub recording"
    replayed = ValhallaClient(base_url="http://unused.invalid", mode="replay", cassette_dir=tmp_path)
    assert replayed.isochrone(ISO_BODY) == first
    assert len(seen) == 1  # replay made no HTTP call


def test_changed_request_does_not_reuse_recording(tmp_path: Path, stub_server: tuple[str, Any]) -> None:
    url, _ = stub_server
    ValhallaClient(base_url=url, mode="record", cassette_dir=tmp_path).isochrone(ISO_BODY)
    other = dict(ISO_BODY, costing="bicycle")
    with pytest.raises(CassetteMissing):
        ValhallaClient(mode="replay", cassette_dir=tmp_path).isochrone(other)


def test_hand_edited_cassette_is_rejected(tmp_path: Path, stub_server: tuple[str, Any]) -> None:
    url, _ = stub_server
    ValhallaClient(base_url=url, mode="record", cassette_dir=tmp_path).isochrone(ISO_BODY)
    p = cassette_path(tmp_path, "isochrone", ISO_BODY)
    doc = json.loads(p.read_text())
    doc["request"]["costing"] = "pedestrian"
    p.write_text(json.dumps(doc))
    with pytest.raises(CassetteMissing, match="different request"):
        ValhallaClient(mode="replay", cassette_dir=tmp_path).isochrone(ISO_BODY)


def test_unknown_endpoint_and_bad_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        ValhallaClient().post("optimized_route", {})
    monkeypatch.setenv("VALHALLA_MODE", "sometimes")
    with pytest.raises(ValueError):
        ValhallaClient.from_env()
    monkeypatch.setenv("VALHALLA_MODE", "replay")
    assert ValhallaClient.from_env(CASSETTES).mode == "replay"


def test_matrix_parsers_both_shapes() -> None:
    concise = {"sources_to_targets": {"durations": [[60, None], [120, 180]]}}
    verbose = {
        "sources_to_targets": [
            [{"from_index": 0, "to_index": 0, "time": 60}, {"from_index": 0, "to_index": 1, "time": None}],
            [{"from_index": 1, "to_index": 0, "time": 120}, {"from_index": 1, "to_index": 1, "time": 180}],
        ]
    }
    want = {("a", "F"): 1.0, ("b", "F"): 2.0, ("b", "G"): 3.0}
    assert parse_matrix_minutes(concise, ["a", "b"], ["F", "G"]) == want
    assert parse_matrix_minutes(verbose, ["a", "b"], ["F", "G"]) == want
    with pytest.raises(ValueError):
        parse_matrix_minutes(concise, ["a"], ["F", "G"])
    with pytest.raises(ValueError):
        parse_matrix_minutes({"durations": []}, [], [])


def test_matrix_request_rounds_coordinates() -> None:
    body = matrix_request([(37.123456789, -121.1)], [(37.2, -121.987654321)])
    assert body["sources"] == [{"lat": 37.123457, "lon": -121.1}]
    assert body["targets"] == [{"lat": 37.2, "lon": -121.987654}] and body["costing"] == "auto"


def test_committed_cassettes_are_labelled_synthetic() -> None:
    files = sorted(CASSETTES.glob("*.json"))
    assert files
    for f in files:
        doc = json.loads(f.read_text())
        assert "SYNTHETIC" in doc["_note"] and "NOT recorded from a Valhalla server" in doc["_note"]
        assert f.name == cassette_path(CASSETTES, doc["endpoint"], doc["request"]).name
