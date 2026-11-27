"""Load and gate `data/catalog/releases.yaml` (ADR-001 #3).

CLI: ``python -m spine.catalog.releases <releases.yaml> [...]`` validates every file and exits 1
on any error (bad row, duplicate id, a 'latest' reference).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from spine.catalog.models import DatasetRelease


class CatalogError(ValueError):
    pass


def load_catalog(path: str | Path) -> dict[str, DatasetRelease]:
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("releases") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise CatalogError(f"{path}: expected a top-level 'releases' list")
    out: dict[str, DatasetRelease] = {}
    for i, row in enumerate(rows):
        try:
            rel = DatasetRelease.model_validate(row)
        except ValidationError as e:
            raise CatalogError(f"{path}: row {i}: {e}") from e
        if rel.release_id in out:
            raise CatalogError(f"{path}: duplicate release_id {rel.release_id!r}")
        out[rel.release_id] = rel
    return out


def assert_publishable(catalog: dict[str, DatasetRelease], release_ids: Iterable[str]) -> None:
    """Fail when a build references an unknown release or one not yet pinned by checksum."""
    errs: list[str] = []
    for rid in release_ids:
        rel = catalog.get(rid)
        if rel is None:
            errs.append(f"{rid}: not in releases.yaml")
        elif rel.status != "pinned":
            errs.append(f"{rid}: status {rel.status}, sha256 not pinned yet")
    if errs:
        raise CatalogError("; ".join(errs))


def as_guard_releases(catalog: dict[str, DatasetRelease]) -> list[dict[str, Any]]:
    """Shape the catalog the way tools/ci/license_guard.py reads it."""
    return [
        {"release_id": r.release_id, "license_class": r.license_class.value, "status": r.status}
        for r in catalog.values()
    ]


def main(argv: list[str]) -> int:
    rc = 0
    for p in argv[1:]:
        try:
            cat = load_catalog(p)
        except CatalogError as e:
            print(f"CATALOG FAIL {e}")
            rc = 1
            continue
        pending = sum(1 for r in cat.values() if r.status == "pending_download")
        print(f"CATALOG OK {p}: {len(cat)} releases ({pending} pending_download)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
