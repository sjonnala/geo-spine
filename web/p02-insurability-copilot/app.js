/* Product 02 Evidence & Mitigation Appeal Card. Zero build: reads data/cards.json (synthetic fixture
 * export from tools/fixtures/make_butte_fixtures.py). Copy rules (G-103 2.5, gate G2.3):
 *  - the only number is "Documentation completeness", always labelled "not a risk score";
 *  - when abstaining: "We can't score this home yet: <reason>." and the checklist stays visible;
 *  - no owner name, address, APN or grid cell id is ever in the data or on the page. */
(function () {
  "use strict";

  var EVIDENCE_WORDS = {
    open_data_observed: "seen in pinned open data",
    owner_attested_with_photo: "your attestation with a photo",
    owner_attested: "your attestation",
    unknown: "no evidence yet"
  };
  var LETTER_TITLES = {
    score_request: "Request your score (h)",
    revised_score_request: "Request a revised score after mitigation (h)(4)",
    appeal: "Appeal (i)"
  };
  var state = { cards: [], current: null };

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    if (cls) {
      node.className = cls;
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function fmt1(v) {
    return v === null || v === undefined ? "n/a" : Number(v).toFixed(1);
  }

  function renderFacts(card) {
    var dl = document.getElementById("facts");
    clear(dl);
    var od = card.open_data;
    var rows = [
      ["Structure", card.structure_id + " (synthetic)"],
      ["Kind", card.structure_kind.replace("_", " ")],
      ["Vegetation within 0 to 5 ft (NAIP)", od.naip_veg_0_5ft_pct === null ? "not measured" : fmt1(od.naip_veg_0_5ft_pct) + "%"],
      ["Tree canopy in grid cell (LANDFIRE)", od.canopy_cover_pct === null ? "no data" : fmt1(od.canopy_cover_pct) + "%"],
      ["Slope in grid cell (3DEP)", od.slope_deg === null ? "no data" : fmt1(od.slope_deg) + " degrees"],
      ["Open-data exposure context", od.exposure_context === null ? "no data" : od.exposure_context + " (a description, not an insurer's score)"]
    ];
    rows.forEach(function (r) {
      dl.appendChild(el("dt", r[0], "muted"));
      dl.appendChild(el("dd", r[1]));
    });
  }

  function renderScore(card) {
    var panel = document.getElementById("score-panel");
    clear(panel);
    if (card.verdict === "abstain") {
      var box = el("div", null, "abstain");
      box.appendChild(el("p", "We can't score this home yet: " + card.abstain_messages[0] + "."));
      card.abstain_messages.slice(1).forEach(function (m) {
        box.appendChild(el("p", "Also: " + m + ".", "muted"));
      });
      box.appendChild(el("p", "The checklist below still shows what to document. The score and the appeal stay withheld.", "muted"));
      panel.appendChild(box);
      return;
    }
    var s = card.score;
    panel.appendChild(el("div", fmt1(s.total) + " / 100", "score"));
    var meter = el("div", null, "meter");
    var fill = el("span");
    fill.style.width = Math.max(0, Math.min(100, s.total)) + "%";
    meter.appendChild(fill);
    panel.appendChild(meter);
    panel.appendChild(el("p", "Documentation completeness (not a risk score; insurers use their own models).", "muted"));
    var ul = el("ul", null, "blocks");
    [["Community", s.community, 20], ["Surroundings", s.surroundings, 40], ["Hardening", s.hardening, 40]].forEach(function (b) {
      var li = el("li");
      li.appendChild(el("span", b[0]));
      li.appendChild(el("span", fmt1(b[1]) + " / " + b[2]));
      ul.appendChild(li);
    });
    panel.appendChild(ul);
    var missing = card.checklist.filter(function (r) { return r.evidence === "unknown"; }).length;
    panel.appendChild(el("p", card.ready ? "Ready to request your score and appeal." : "Document more items first (" + missing + " still need evidence).", card.ready ? "ready" : "muted"));
  }

  function renderChecklist(card) {
    var tbody = document.getElementById("checklist");
    clear(tbody);
    card.checklist.forEach(function (r) {
      var tr = el("tr", null, r.evidence === "unknown" ? "unknown" : "");
      tr.appendChild(el("td", r.label));
      tr.appendChild(el("td", r.subdivision));
      tr.appendChild(el("td", EVIDENCE_WORDS[r.evidence]));
      tr.appendChild(el("td", r.strength.toFixed(1), "num"));
      tbody.appendChild(tr);
    });
  }

  function readDates() {
    var dates = {};
    Array.prototype.forEach.call(document.querySelectorAll("#date-inputs input"), function (input) {
      dates[input.getAttribute("data-field")] = input.value;
    });
    return dates;
  }

  function renderDeadlines() {
    var tbody = document.getElementById("deadlines");
    clear(tbody);
    var rows = window.P02Deadlines.computeDeadlines(readDates());
    if (!rows.length) {
      var tr = el("tr");
      var td = el("td", "Enter a date above to see the insurer's deadlines.", "muted");
      td.colSpan = 3;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    rows.forEach(function (d) {
      var row = el("tr");
      row.appendChild(el("td", d.description));
      row.appendChild(el("td", d.rule));
      row.appendChild(el("td", d.due));
      tbody.appendChild(row);
    });
  }

  function renderLetters(card) {
    var box = document.getElementById("letters");
    clear(box);
    Object.keys(LETTER_TITLES).forEach(function (key) {
      if (!card.letters[key]) {
        return;
      }
      var det = el("details");
      det.appendChild(el("summary", LETTER_TITLES[key] + " (draft, you send it)"));
      det.appendChild(el("pre", card.letters[key]));
      box.appendChild(det);
    });
    document.getElementById("memo").textContent = card.memo_md;
  }

  function show(id) {
    var card = state.cards.filter(function (c) { return c.structure_id === id; })[0];
    if (!card) {
      return;
    }
    state.current = card;
    renderFacts(card);
    renderScore(card);
    renderChecklist(card);
    renderLetters(card);
    renderDeadlines();
  }

  function init(data) {
    state.cards = data.cards;
    document.getElementById("attribution").textContent = data.attribution;
    var picker = document.getElementById("picker");
    data.cards.forEach(function (c) {
      var label = c.structure_id + " · " + (c.verdict === "abstain" ? "can't score yet (" + c.abstain_reasons[0] + ")" : c.verdict === "recommend" ? "ready" : "document more");
      var opt = el("option", label);
      opt.value = c.structure_id;
      picker.appendChild(opt);
    });
    picker.addEventListener("change", function () { show(picker.value); });
    Array.prototype.forEach.call(document.querySelectorAll("#date-inputs input"), function (input) {
      input.addEventListener("change", renderDeadlines);
    });
    show(data.cards[0].structure_id);
  }

  fetch("data/cards.json")
    .then(function (r) { return r.json(); })
    .then(init)
    .catch(function (err) {
      document.getElementById("score-panel").textContent = "Could not load data/cards.json: " + err;
    });
})();
