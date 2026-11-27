"""web/p02-insurability-copilot: static checks, copy rules and Python/JavaScript deadline parity."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date

import pytest

from spine.decision import insurability_copilot as ic
from spine.surface.p02_memo import SYNTHETIC_BANNER
from support.p02 import P02_WEB, assessments

HTML = (P02_WEB / "index.html").read_text(encoding="utf-8")
JS = (P02_WEB / "app.js").read_text(encoding="utf-8")
DEADLINES_JS = P02_WEB / "deadlines.js"
CARDS = json.loads((P02_WEB / "data" / "cards.json").read_text(encoding="utf-8"))
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def test_no_third_party_scripts_and_draft_only() -> None:
    srcs = re.findall(r'<script[^>]*src="([^"]+)"', HTML)
    assert srcs == ["deadlines.js", "app.js"]
    assert "draft only" in _text(HTML).lower() and "Synthetic fixture data for CI." in _text(HTML)
    assert SYNTHETIC_BANNER.startswith("_Synthetic fixture data for CI.")  # the memo says the same
    assert not re.search(r"fetch\(\s*['\"]https?:", JS)  # the viewer contacts nobody


def test_risk_score_only_ever_negated() -> None:
    blob = HTML + JS + json.dumps(CARDS, ensure_ascii=False)
    hits = list(re.finditer(r"risk score", blob, flags=re.IGNORECASE))
    assert hits
    for m in hits:
        assert blob[max(0, m.start() - 7) : m.start()].lower().endswith("not a "), blob[
            m.start() - 40 : m.end()
        ]


def test_cards_match_assessments() -> None:
    got = {c["structure_id"]: c for c in CARDS["cards"]}
    assert set(got) == set(assessments())
    for sid, a in assessments().items():
        c = got[sid]
        assert c["verdict"] == a.recommendation.verdict and c["grounding_passed"]
        assert len(c["checklist"]) == 12
        assert (c["score"] is None) == a.gate.abstain
        assert c["ready"] == a.ready_to_appeal
        if a.gate.abstain:
            assert c["abstain_messages"] and "appeal" not in c["letters"]


@NODE
@pytest.mark.parametrize("name", ["app.js", "deadlines.js"])
def test_js_parses(name: str) -> None:
    subprocess.run(["node", "--check", str(P02_WEB / name)], check=True)


@NODE
def test_deadlines_js_matches_python() -> None:
    cases = [
        ic.UserDates(
            application_completed=date(2027, 1, 4),
            renewal=date(2027, 3, 1),
            nonrenewal_effective=date(2027, 3, 1),
            revised_score_requested=date(2027, 2, 1),
            appeal_received=date(2027, 2, 10),
        ),
        ic.UserDates(renewal=date(2028, 3, 1), appeal_received=date(2028, 2, 20)),  # leap year
        ic.UserDates(nonrenewal_effective=date(2027, 1, 1)),  # crosses a year boundary
        ic.UserDates(),
    ]
    payload = [{k: v.isoformat() for k, v in vars(d).items() if v} for d in cases]
    script = (
        f"const d = require({json.dumps(str(DEADLINES_JS))});"
        f"const cases = {json.dumps(payload)};"
        "process.stdout.write(JSON.stringify({days: d.DAYS, out: cases.map(d.computeDeadlines)}));"
    )
    res = json.loads(
        subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout
    )
    want = [
        [
            {"key": x.key, "rule": x.rule, "due": x.due.isoformat(), "description": x.description}
            for x in ic.compute_deadlines(d)
        ]
        for d in cases
    ]
    assert res["out"] == want
    assert res["days"] == {
        "score_after_application": ic.SCORE_AFTER_APPLICATION_DAYS,
        "score_before_renewal": ic.SCORE_BEFORE_RENEWAL_DAYS,
        "score_before_nonrenewal": ic.SCORE_BEFORE_NONRENEWAL_DAYS,
        "revised_score": ic.REVISED_SCORE_DAYS,
        "appeal_acknowledgement": ic.APPEAL_ACK_DAYS,
        "appeal_decision": ic.APPEAL_DECISION_DAYS,
    }


def test_date_inputs_cover_every_rule() -> None:
    fields = set(re.findall(r'data-field="([a-z_]+)"', HTML))
    assert fields == {f.name for f in ic.UserDates.__dataclass_fields__.values()}
