# ADR-005: Licensing separation and privacy guardrails

- **Status:** Accepted (G-102 approved; implemented in `tools/ci/license_guard.py` with the Director audit fixes)

## Decision [D]
`license_guard.py` runs in CI over a build manifest listing every artifact, its input `release_id`s, columns,
grain and publish flags (`make license-guard` checks `data/manifests/p01_santa_clara_fixture.json`).

| Rule | Check | Why |
|---|---|---|
| **L1 ODbL isolation** | An artifact mixing ODbL (share-alike) inputs with any other class fails unless declared `produced_work: true` (rendered tiles, maps, aggregated statistics) or itself released under ODbL-1.0 | Keeps OSM-derived routing data from contaminating other datasets (G-101 Q4: Produced Work, Collective Database) |
| **L2 NC quarantine** | Any artifact with a non-commercial input must sit under `quarantine/nc/` and not be flagged `commercial` | Carbon Mapper is NC under its **own custom Terms of Use (13 Jan 2026), not CC BY-NC** (G-101 correction) |
| **L3 Catalog completeness** | Every input must exist in the catalog | No silent data |
| **L4 Restricted in commercial** | An artifact flagged `commercial: true` with a `restricted` input (e.g. CDSS) fails unless every such release is listed in `restricted_approvals` and a non-empty `restricted_approval_ref` records the approval | CDSS commercial use needs CHHS approval (G-101); added in G-301 |
| **P1 No person-level columns** | Column names matching owner, taxpayer, grantee, occupant, resident, household_member, first/last/full name, **licensee / licensee_name**, phone, email, SSN or DOB fail | No owner-name or individual joins; CDSS licensee names never leak |
| **P2 Household grain** | Public structure-level outputs need `k_anon_min >= 10` or aggregation to res 8 | Survivor and insurability outputs must not identify a home |

Thresholds (k=10, the column regex) are [D] and should be reviewed. Engineering guardrails, not legal advice.

## Director audit fixes (G-102 → G-201)
1. **Unknown release KeyError:** `unknown = [i for i in a["inputs"] if i not in rel]` now runs *before*
   `classes = {rel[i]["license_class"] for i in a["inputs"] if i in rel}`, so an unknown `release_id` is
   reported as an L3 error instead of crashing. Unit-tested (`test_unknown_release_id_reported_not_keyerror`).
2. **Licensee names:** `licensee` / `licensee_name` added to `PII_COLS`; parametrised tests cover both and
   confirm `licensed_capacity` is not caught. Curation (`spine.identity.facilities`) also drops the raw column.

## Product 01 boundary [D: Director to confirm]
The P01 gap scores and memo combine ODbL catchments with ACS and CDSS counts. The manifest declares them
`produced_work: true` as aggregated statistics per catchment; `catchment_cells` itself is published under
ODbL-1.0. A test proves the guard fails if that declaration is removed. CDSS is pinned `restricted`
(commercial use needs CHHS approval), so P01 artifacts are flagged `commercial: false`. Rule L4 (G-301) now
fails any commercial artifact with a `restricted` input unless the approval is recorded in the manifest.
