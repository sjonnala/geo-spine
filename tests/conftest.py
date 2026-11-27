from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures"
ISO_FIXTURE = FX / "valhalla" / "isochrone_santa_clara_synthetic.json"
ORIGIN = "8828347029fffff"  # res 8 cell at the synthetic Santa Clara origin


@pytest.fixture(scope="session")
def iso_payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ISO_FIXTURE.read_text(encoding="utf-8"))
    return data
