"""Valhalla HTTP client with a recorded-response (VCR-style) test mode, stdlib only.

Modes:

* ``live``   POST to a running Valhalla server (``docker/valhalla/compose.yaml``).
* ``record`` POST live, then save request + response as a cassette file.
* ``replay`` never touches the network: answer from a cassette, or raise ``CassetteMissing``.

CI only ever runs ``replay``. A cassette is keyed by the endpoint plus the canonical JSON of the
request body, so a changed request can never silently reuse an old response.

Endpoints used by the spine: ``/isochrone`` (Kernel #1) and ``/sources_to_targets`` (the one
origin-destination table 2SFCA needs, G-103 section 1.2). The matrix parser accepts the verbose
``sources_to_targets`` list-of-lists shape and the concise ``durations`` shape; exact parameters
of the live service are still unverified against a running server [U].
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Mode = Literal["live", "record", "replay"]
ENDPOINTS = ("isochrone", "sources_to_targets", "route", "status")
DEFAULT_URL = "http://localhost:8002"


class CassetteMissing(LookupError):
    """Replay mode found no recording for this exact request."""


def request_key(endpoint: str, body: dict[str, Any]) -> str:
    canon = json.dumps({"endpoint": endpoint, "body": body}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def cassette_path(cassette_dir: Path, endpoint: str, body: dict[str, Any]) -> Path:
    return cassette_dir / f"{endpoint}-{request_key(endpoint, body)[:16]}.json"


@dataclass
class ValhallaClient:
    base_url: str = DEFAULT_URL
    mode: Mode = "replay"
    cassette_dir: Path | None = None
    timeout_s: float = 30.0
    note: str = "Recorded from a live Valhalla server."
    calls: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, cassette_dir: Path | None = None) -> ValhallaClient:
        mode = os.environ.get("VALHALLA_MODE", "replay")
        if mode not in ("live", "record", "replay"):
            raise ValueError(f"VALHALLA_MODE must be live, record or replay (got {mode!r})")
        url = os.environ.get("VALHALLA_URL", DEFAULT_URL)
        return cls(base_url=url, mode=mode, cassette_dir=cassette_dir)  # type: ignore[arg-type]

    def post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        if endpoint not in ENDPOINTS:
            raise ValueError(f"unknown Valhalla endpoint {endpoint!r}")
        self.calls.append(endpoint)
        if self.mode == "replay":
            return self._replay(endpoint, body)
        response = self._live(endpoint, body)
        if self.mode == "record":
            self._record(endpoint, body, response)
        return response

    def isochrone(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.post("isochrone", body)

    def matrix(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.post("sources_to_targets", body)

    def _need_dir(self) -> Path:
        if self.cassette_dir is None:
            raise ValueError(f"{self.mode} mode needs a cassette_dir")
        return self.cassette_dir

    def _replay(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        p = cassette_path(self._need_dir(), endpoint, body)
        if not p.exists():
            raise CassetteMissing(f"no recording {p.name} for this {endpoint} request; re-record it")
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("request") != body:
            raise CassetteMissing(f"{p.name} holds a different request (key collision or hand edit)")
        response: dict[str, Any] = data["response"]
        return response

    def _live(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be http(s)")
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/{endpoint}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 (scheme checked)
            payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return payload

    def _record(self, endpoint: str, body: dict[str, Any], response: dict[str, Any]) -> Path:
        d = self._need_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = cassette_path(d, endpoint, body)
        doc = {"_note": self.note, "endpoint": endpoint, "request": body, "response": response}
        p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return p


def matrix_request(
    sources: Sequence[tuple[float, float]], targets: Sequence[tuple[float, float]], costing: str = "auto"
) -> dict[str, Any]:
    """``POST /sources_to_targets`` body; points are (lat, lon)."""
    return {
        "sources": [{"lat": round(a, 6), "lon": round(b, 6)} for a, b in sources],
        "targets": [{"lat": round(a, 6), "lon": round(b, 6)} for a, b in targets],
        "costing": costing,
    }


def parse_matrix_minutes(
    payload: dict[str, Any], source_ids: Sequence[str], target_ids: Sequence[str]
) -> dict[tuple[str, str], float]:
    """Matrix response -> ``{(source_id, target_id): minutes}``; unreachable pairs are left out."""
    out: dict[tuple[str, str], float] = {}
    stt = payload.get("sources_to_targets")
    if not isinstance(stt, (dict, list)):
        raise ValueError("expected a sources_to_targets matrix response")
    if len(source_ids) != _rows(stt):
        raise ValueError("matrix has a different number of sources than ids given")
    if isinstance(stt, dict):  # concise shape: {"durations": [[seconds|null, ...], ...]}
        grid = stt["durations"]
        for i, row in enumerate(grid):
            if len(row) != len(target_ids):
                raise ValueError("matrix has a different number of targets than ids given")
            for j, sec in enumerate(row):
                if sec is not None:
                    out[(source_ids[i], target_ids[j])] = float(sec) / 60.0
    elif isinstance(stt, list):  # verbose shape: [[{"from_index", "to_index", "time"}, ...], ...]
        for row in stt:
            for cellv in row:
                if cellv.get("time") is not None:
                    key = (source_ids[cellv["from_index"]], target_ids[cellv["to_index"]])
                    out[key] = float(cellv["time"]) / 60.0
    return out


def _rows(stt: Any) -> int:
    return len(stt["durations"]) if isinstance(stt, dict) else len(stt)
