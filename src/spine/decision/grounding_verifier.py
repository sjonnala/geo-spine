"""ADR-004: deterministic numeric-grounding verifier (stdlib only).

Every number in an LLM- or template-written memo must match a deterministic feature row (value
within tolerance) AND at least one matching row's release_id must be cited in the memo.
Otherwise CI fails. `Memo.grounding_passed` is set only from this tool's result.

CLI: ``python -m spine.decision.grounding_verifier <memo.md> <features.json>`` where the JSON is
``{"allowed_releases": [...], "rows": [{"feature_id", "value", "unit", "release_id"}, ...]}``.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

NUM_RE = re.compile(r"(?<![\w.])[-+]?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![\w])")
CITE_RE = re.compile(r"\[src:([A-Za-z0-9_.\-]+)\]")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
ORDINAL_RE = re.compile(r"^\s*\d+\.\s")
# ADR-004 known limit: spelled-out numbers slip past NUM_RE, so a second pass flags them.
NUMBER_WORD_RE = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
    r"ninety|hundred|thousand|million|billion|dozen)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FeatureRow:
    feature_id: str
    value: Decimal
    unit: str
    release_id: str
    tolerance_abs: Decimal = Decimal("0")
    tolerance_rel: Decimal = Decimal("0.005")  # 0.5% for rounding in prose


@dataclass(frozen=True)
class Finding:
    token: str
    reason: str
    line: int


def normalise(tok: str) -> tuple[Decimal | None, str]:
    unit = "%" if tok.endswith("%") else ("$" if "$" in tok else "")
    raw = tok.replace("$", "").replace("%", "").replace(",", "")
    try:
        return Decimal(raw), unit
    except InvalidOperation:
        return None, unit


def matches(v: Decimal, unit: str, row: FeatureRow) -> bool:
    if unit and row.unit and unit != row.unit:
        return False
    tol = max(row.tolerance_abs, abs(row.value) * row.tolerance_rel)
    return abs(v - row.value) <= tol


def verify(
    memo: str,
    rows: Iterable[FeatureRow],
    allowed_releases: set[str],
    *,
    flag_number_words: bool = True,
) -> list[Finding]:
    rows = list(rows)
    findings: list[Finding] = []
    cited = set(CITE_RE.findall(memo))
    for bad in sorted(cited - allowed_releases):
        findings.append(Finding(bad, "citation not in pinned releases.yaml", 0))
    for ln, line in enumerate(memo.splitlines(), 1):
        stripped = CITE_RE.sub("", line)  # citation ids are not claims
        stripped = ORDINAL_RE.sub("", stripped)  # ordered-list ordinals
        if flag_number_words:
            for w in NUMBER_WORD_RE.finditer(stripped):
                findings.append(
                    Finding(w.group(0), "spelled-out number; write digits so it can be checked", ln)
                )
        for m in NUM_RE.finditer(stripped):
            tok = m.group(0)
            if YEAR_RE.match(tok):
                # Years are allowed only if a cited release carries that vintage.
                if not any(tok in r for r in cited):
                    findings.append(Finding(tok, "year/vintage not backed by a cited release", ln))
                continue
            v, unit = normalise(tok)
            if v is None:
                findings.append(Finding(tok, "unparseable number", ln))
                continue
            hits = [r for r in rows if matches(v, unit, r)]
            if not hits:
                findings.append(Finding(tok, "no deterministic feature row matches", ln))
                continue
            if not any(r.release_id in cited for r in hits):
                findings.append(Finding(tok, "matching row's release_id not cited in memo", ln))
    return findings


def rows_from_payload(payload: dict[str, Any]) -> list[FeatureRow]:
    return [
        FeatureRow(r["feature_id"], Decimal(str(r["value"])), r.get("unit", ""), r["release_id"])
        for r in payload["rows"]
    ]


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as f:
        memo = f.read()
    with open(argv[2], encoding="utf-8") as f:
        payload = json.load(f)
    findings = verify(memo, rows_from_payload(payload), set(payload["allowed_releases"]))
    for fd in findings:
        print(f"GROUNDING FAIL line {fd.line}: {fd.token!r} -> {fd.reason}")
    print("GROUNDING OK" if not findings else f"{len(findings)} ungrounded claim(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
