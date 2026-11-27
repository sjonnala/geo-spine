PY ?= python3

.PHONY: ci test lint typecheck boundaries license-guard verify-memos catalog fixtures

ci: lint typecheck boundaries catalog license-guard verify-memos test

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tools tests
	$(PY) -m ruff format --check src tools tests

typecheck:
	$(PY) -m mypy src tools/ci tools/fixtures

boundaries:
	lint-imports

catalog:
	$(PY) -m spine.catalog.releases data/catalog/releases.yaml tests/fixtures/releases.fixture.yaml

license-guard:
	$(PY) tools/ci/license_guard.py data/manifests/p01_santa_clara_fixture.json \
		--catalog tests/fixtures/releases.fixture.yaml

verify-memos:
	$(PY) -m spine.decision.grounding_verifier tests/fixtures/memos/p01_santa_clara_memo.md \
		tests/fixtures/memos/p01_santa_clara_features.json

# Regenerate the synthetic Santa Clara fixtures (deterministic) and their pinned checksums.
fixtures:
	PYTHONPATH=src $(PY) tools/fixtures/make_santa_clara_fixtures.py
