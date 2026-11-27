PY ?= python3

.PHONY: ci test lint typecheck boundaries license-guard verify-memos catalog web fixtures tiles valhalla-up

ci: lint typecheck boundaries catalog license-guard verify-memos web test

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

# Static viewer: the JavaScript must parse (no build step, no bundler).
web:
	node --check web/p01-access-gap/app.js

# Regenerate the synthetic Santa Clara fixtures (deterministic) and their pinned checksums.
fixtures:
	PYTHONPATH=src $(PY) tools/fixtures/make_santa_clara_fixtures.py

# Product 01 PMTiles from the fixture export (needs tippecanoe; not part of `make ci`).
tiles:
	PYTHONPATH=src $(PY) -c "import json; from spine.surface.p01_tiles import write_geojsonseq; \
		write_geojsonseq(json.load(open('web/p01-access-gap/data/cells.geojson')), 'tiles/01/cells.geojsonseq')"
	tippecanoe -o tiles/01/fixture-g301.pmtiles -zg --drop-densest-as-needed --force -l cells \
		tiles/01/cells.geojsonseq

# Local Valhalla (pinned multi-arch image); see docker/valhalla/compose.yaml for sizing notes.
valhalla-up:
	docker compose -f docker/valhalla/compose.yaml up -d
