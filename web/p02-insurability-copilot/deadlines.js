/* Product 02 deadline calendar: pure date arithmetic from dates the homeowner enters.
 * Mirrors spine.decision.insurability_copilot.compute_deadlines (parity-tested from pytest via node).
 * Day counts come from 10 CCR § 2644.9 (h), (h)(4) and (i) as read for G-103 section 2.3. */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.P02Deadlines = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var DAYS = {
    score_after_application: 15,
    score_before_renewal: 45,
    score_before_nonrenewal: 75,
    revised_score: 30,
    appeal_acknowledgement: 10,
    appeal_decision: 30
  };

  // [key, input field, sign, rule, description]
  var RULES = [
    ["score_after_application", "application_completed", 1, "(h)",
      "Latest date for your written score after a completed application"],
    ["score_before_renewal", "renewal", -1, "(h)",
      "Latest date for your written score before renewal"],
    ["score_before_nonrenewal", "nonrenewal_effective", -1, "(h)",
      "Latest date for your written score before a nonrenewal takes effect"],
    ["revised_score", "revised_score_requested", 1, "(h)(4)",
      "Latest date for a revised score after your mitigation request"],
    ["appeal_acknowledgement", "appeal_received", 1, "(i)",
      "Latest date for the insurer's written acknowledgement of your appeal"],
    ["appeal_decision", "appeal_received", 1, "(i)",
      "Latest date for the insurer's decision on your appeal"]
  ];

  var ISO = /^(\d{4})-(\d{2})-(\d{2})$/;
  var DAY_MS = 86400000;

  function parseIso(text) {
    var m = ISO.exec(text || "");
    if (!m) {
      return null;
    }
    return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }

  function formatIso(ms) {
    return new Date(ms).toISOString().slice(0, 10);
  }

  function computeDeadlines(dates) {
    var out = [];
    RULES.forEach(function (r) {
      var start = parseIso(dates[r[1]]);
      if (start === null) {
        return;
      }
      out.push({ key: r[0], rule: r[3], due: formatIso(start + r[2] * DAYS[r[0]] * DAY_MS), description: r[4] });
    });
    out.sort(function (a, b) {
      if (a.due !== b.due) {
        return a.due < b.due ? -1 : 1;
      }
      return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
    });
    return out;
  }

  return { DAYS: DAYS, computeDeadlines: computeDeadlines };
});
