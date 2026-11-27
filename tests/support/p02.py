"""Shared Product 02 test helpers: the fixture generator module and the synthetic build."""

from __future__ import annotations

import importlib.util
from functools import cache
from pathlib import Path
from types import ModuleType

from spine.catalog.models import DatasetRelease
from spine.catalog.releases import load_catalog
from spine.decision.insurability_copilot import P02Assessment

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "tests" / "fixtures"
BUTTE = FX / "butte"
P02_CATALOG = FX / "releases_p02.fixture.yaml"
P02_MANIFEST = ROOT / "data" / "manifests" / "p02_butte_fixture.json"
P02_WEB = ROOT / "web" / "p02-insurability-copilot"


@cache
def gen() -> ModuleType:
    """tools/fixtures/make_butte_fixtures.py, imported by path (tools/ is not a package)."""
    path = ROOT / "tools" / "fixtures" / "make_butte_fixtures.py"
    spec = importlib.util.spec_from_file_location("make_butte_fixtures", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def catalog() -> dict[str, DatasetRelease]:
    return load_catalog(P02_CATALOG)


def committed_sources() -> dict[str, str]:
    return {k: (ROOT / k).read_text(encoding="utf-8") for k in gen().source_files()}


@cache
def assessments() -> dict[str, P02Assessment]:
    g = gen()
    out = g.assess_all(committed_sources(), catalog(), g.fake_grid)
    return {a.subject_id: a for a in out}
