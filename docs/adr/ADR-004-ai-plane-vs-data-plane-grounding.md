# ADR-004: AI plane vs data plane, and the numeric grounding verifier

- **Status:** Accepted (G-102 approved; implemented in `src/spine/decision/grounding_verifier.py`)

## Decision [D]
The AI plane (LLM) may only narrate, rank prose or extract structure. It never computes a number. Every
figure in a memo comes from the data plane: a deterministic feature row with a pinned `release_id`. The CI
gate `make verify-memos` runs the verifier over every memo before publish, and `Memo.grounding_passed` is set
only from its result.

## Algorithm
1. Collect citations `[src:<release_id>]`. A cited id not in the pinned catalog fails.
2. Strip citation tokens and list ordinals, then extract numeric tokens: integers, thousands-separated
   numbers, decimals, `%` and `$`.
3. **Years:** a four-digit year passes only if it appears inside a cited `release_id`.
4. **Every other number** must match a feature row with compatible units within
   `max(abs_tol, 0.5% × |value|)`, and at least one matching row's `release_id` must be cited.
5. Parameters such as "15-minute" are not exempt: kernels emit them as `param_*` feature rows.
6. Output one `GROUNDING FAIL line N: token -> reason` per violation; exit 1 on any failure.

## Known limits, and the G-201 mitigation
- Spelled-out numbers ("twelve") slip past step 2. **Implemented in G-201:** a second regex pass flags number
  words (on by default; `flag_number_words=False` turns it off). Product copy is written without them.
- A hallucinated number that equals a feature value within tolerance passes. Mitigation: give each memo only
  its subject's feature rows.

## Product 01 use
`spine.surface.p01_memo` renders the Santa Clara memo from a deterministic template (no LLM yet) and runs the
verifier; the fixture memo and its rows are in `tests/fixtures/memos/` and checked by `make verify-memos`.
