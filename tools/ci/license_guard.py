"""ADR-005 CI guard (stdlib + optional PyYAML for --catalog).

Input: a build manifest JSON listing every output artifact, its input release_ids, its column
names, its grain and its publish flags. Releases come from the manifest's "releases" list or,
with ``--catalog <releases.yaml>``, from a catalog file.

Rules: L1 ODbL isolation, L2 NC quarantine, L3 catalog completeness, L4 restricted inputs stay
out of commercial artifacts without an explicit approval, P1 no person-level columns, P2 household
grain. Engineering guardrails, not legal advice.

L4 (G-301): a ``restricted`` release (e.g. CDSS childcare licensing data, whose CHHS terms require
approval for commercial use, G-101 Q5) may feed an artifact flagged ``commercial: true`` only if
that artifact lists the release_id in ``restricted_approvals`` with a non-empty
``restricted_approval_ref`` pointing at the written approval. A bare ``true`` is not enough.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

# Director audit fix (G-102): licensee / licensee_name added so CDSS licensee names never leak.
PII_COLS = re.compile(
    r"(owner|taxpayer|grantee|occupant|resident|household_member|first_name|last_name|full_name|"
    r"licensee|licensee_name|phone|email|ssn|dob)",
    re.I,
)


def check(manifest: dict[str, Any]) -> list[str]:
    rel = {r["release_id"]: r for r in manifest["releases"]}
    errs: list[str] = []
    for a in manifest["artifacts"]:
        name = a["name"]
        # Director audit fix (G-102): find unknown inputs BEFORE looking up licence classes, so an
        # unknown release_id is reported (rule L3) instead of raising KeyError.
        unknown = [i for i in a["inputs"] if i not in rel]
        if unknown:
            errs.append(f"{name}: inputs not in releases.yaml: {unknown}")
        classes = {rel[i]["license_class"] for i in a["inputs"] if i in rel}
        # Rule L1: ODbL data may enter a mixed artifact only as a Produced Work (rendered/aggregated
        # output) or inside an artifact that is itself released under ODbL (derivative db).
        mixed_odbl = "share_alike" in classes and len(classes) > 1
        declared = a.get("produced_work") or a.get("license") == "ODbL-1.0"
        if mixed_odbl and not declared:
            others = sorted(classes - {"share_alike"})
            errs.append(f"{name}: ODbL input mixed with {others} outside a declared Produced Work boundary")
        # Rule L2: non-commercial inputs are quarantined to artifacts flagged noncommercial.
        if "non_commercial" in classes and a.get("commercial", False):
            errs.append(f"{name}: non-commercial input in a commercial artifact")
        if "non_commercial" in classes and not a["path"].startswith("quarantine/nc/"):
            errs.append(f"{name}: NC-derived artifact must live under quarantine/nc/")
        # Rule L4: restricted inputs (commercial use needs the publisher's approval) never reach a
        # commercial artifact unless each one is approved by release_id, with a reference.
        if a.get("commercial", False):
            restricted = sorted(
                i for i in a["inputs"] if i in rel and rel[i]["license_class"] == "restricted"
            )
            listed = a.get("restricted_approvals")
            approved = {str(x) for x in listed} if isinstance(listed, list) else set()
            missing = [i for i in restricted if i not in approved]
            if missing:
                errs.append(f"{name}: restricted input {missing} in a commercial artifact without approval")
            elif restricted and not str(a.get("restricted_approval_ref") or "").strip():
                errs.append(f"{name}: restricted_approvals given without a restricted_approval_ref")
        # Rule P1: no person-level columns, ever.
        bad = [c for c in a.get("columns", []) if PII_COLS.search(c)]
        if bad:
            errs.append(f"{name}: PII-like columns {bad}")
        # Rule P2: household-level outputs must be aggregated to >= H3 res 8 with k-anonymity.
        if a.get("grain") == "structure" and a.get("public", False) and not a.get("k_anon_min", 0) >= 10:
            errs.append(f"{name}: public structure-level output needs k_anon_min>=10 or aggregation to res 8")
    return errs


def load_catalog_releases(path: str) -> list[dict[str, Any]]:
    import yaml  # PyYAML; only needed for --catalog

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [{"release_id": r["release_id"], "license_class": r["license_class"]} for r in data["releases"]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--catalog", help="releases.yaml to use instead of the manifest's releases list")
    ns = ap.parse_args(argv)
    with open(ns.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    if ns.catalog:
        manifest["releases"] = load_catalog_releases(ns.catalog)
    errs = check(manifest)
    print("\n".join(errs) or "LICENSE/PRIVACY GUARD OK")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
