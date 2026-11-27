# Product 02 static viewer (`web/p02-insurability-copilot/`)

A zero-build Evidence & Mitigation Appeal Card for the California Insurability Copilot (G-302).
Plain HTML, CSS and two local scripts; no bundler and no third-party scripts. Everything in `data/` is the
**synthetic** Butte County / Paradise fixture export written by `make fixtures-p02`.

```bash
python3 -m http.server -d web/p02-insurability-copilot 8001   # then open http://localhost:8001
```

- Layout follows the G-103 section 2.5 wire-spec: structure panel (schematic rings, open-data figures),
  documentation completeness, evidence per item, rights and deadlines, draft letters, the grounded memo.
- Copy rules: the only number is **documentation completeness**, always labelled "not a risk score". An
  abstaining structure shows "We can't score this home yet: <reason>." and keeps the checklist visible.
- Privacy: no owner name, address, APN or H3 cell id is in `data/cards.json` (tested). Deadline dates are
  typed by the homeowner and computed in the browser by `deadlines.js`, which pytest checks against the
  Python `compute_deadlines` through node.
- Every letter is a draft the homeowner sends. Nothing here contacts an insurer.
