"""Product 02 surface: the ADR-004 grounded memo, the draft letters and the copy rules."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from spine.decision.grounding_verifier import main as verify_cli
from spine.decision.insurability_copilot import build_appeal_packet
from spine.surface.p02_memo import (
    MODEL_ID,
    SYNTHETIC_BANNER,
    build_memo,
    features_payload,
    render_letters,
    render_memo,
    verify_letter,
)
from support.p02 import FX, assessments, gen

MEMOS = FX / "memos"
OK, ABSTAIN = "SYN_BUTTE_0001", "SYN_BUTTE_0005"


def memo_for(sid: str) -> str:
    a = assessments()[sid]
    return render_memo(a, build_appeal_packet(a))


def test_committed_memos_match_the_build() -> None:
    for sid, stem in ((OK, "p02_butte"), (ABSTAIN, "p02_butte_abstain")):
        a = assessments()[sid]
        assert (MEMOS / f"{stem}_memo.md").read_text(encoding="utf-8") == memo_for(sid)
        committed = json.loads((MEMOS / f"{stem}_features.json").read_text(encoding="utf-8"))
        assert committed == json.loads(json.dumps(features_payload(a)))


@pytest.mark.parametrize("sid", sorted(assessments()))
def test_every_fixture_memo_and_letter_is_grounded(sid: str) -> None:
    a = assessments()[sid]
    packet = build_appeal_packet(a)
    memo, findings = build_memo(a, packet, gen().GENERATED_AT)
    assert findings == [] and memo.grounding_passed and memo.model_id == MODEL_ID
    assert memo.cited_releases  # every memo cites pinned releases
    for name, letter in render_letters(a, packet).items():
        assert verify_letter(letter, a) == [], name


def _cli(tmp_path: Path, memo: str, stem: str = "p02_butte") -> int:
    m = tmp_path / "memo.md"
    m.write_text(memo, encoding="utf-8")
    return verify_cli(["v", str(m), str(MEMOS / f"{stem}_features.json")])


def test_cli_passes_committed_memo(tmp_path: Path) -> None:
    assert _cli(tmp_path, memo_for(OK)) == 0


def test_tampered_figure_fails(tmp_path: Path) -> None:
    memo = memo_for(OK)
    assert "62.0 out of 100" in memo
    assert _cli(tmp_path, memo.replace("62.0 out of 100", "70.0 out of 100")) == 1


def test_tampered_open_data_figure_fails(tmp_path: Path) -> None:
    assert _cli(tmp_path, memo_for(OK).replace(": 6.0%", ": 7.5%")) == 1


def test_removed_citation_fails(tmp_path: Path) -> None:
    memo = memo_for(OK).replace(" [src:fixture_landfire_butte_2024]", "")
    assert _cli(tmp_path, memo) == 1


def test_unpinned_citation_fails(tmp_path: Path) -> None:
    memo = memo_for(OK).replace("[src:fixture_3dep_butte_2026-11]", "[src:usgs_3dep_latest]")
    assert _cli(tmp_path, memo) == 1


def test_letter_with_citation_tag_or_unknown_number_fails() -> None:
    a = assessments()[OK]
    letters = render_letters(a, build_appeal_packet(a))
    assert verify_letter(letters["appeal"] + " [src:x]", a)
    assert verify_letter(letters["appeal"].replace("10 calendar days", "7 calendar days"), a)


def test_letters_by_readiness() -> None:
    ok = assessments()[OK]
    assert set(render_letters(ok, build_appeal_packet(ok))) == {
        "score_request",
        "revised_score_request",
        "appeal",
    }
    thin = assessments()["SYN_BUTTE_0002"]
    assert "appeal" not in render_letters(thin, build_appeal_packet(thin))
    for letter in render_letters(ok, build_appeal_packet(ok)).values():
        assert "[src:" not in letter and "[Your name]" in letter and "[policy number]" in letter


def test_copy_rules() -> None:
    for sid in assessments():
        body = memo_for(sid)
        assert body.splitlines()[2] == SYNTHETIC_BANNER
        assert "Draft only" in body
        for m in re.finditer(r"risk score", body, flags=re.IGNORECASE):
            assert body[max(0, m.start() - 7) : m.start()].lower().endswith("not a "), sid
        assert "SYN_BUTTE" in body and not re.search(r"\b(owner|taxpayer|apn)\b", body, flags=re.IGNORECASE)


def test_abstain_memo_withholds_the_score() -> None:
    body = memo_for(ABSTAIN)
    assert "We can't score this home yet" in body
    assert "Documentation completeness:" not in body and "out of 100" not in body
    assert "32.0%" in body  # the open-data figure behind the conflict is still shown, and grounded
