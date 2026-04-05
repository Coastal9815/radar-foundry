/* A9P_RIGHT3_THREAT_JS_V2 — Threat/Conditions + Xweather LTG (10–25 mi yellow, ≤10 mi red w/ hold) */
(function () {
  const POLL_MS = 2500;
  const MAX_CH = 15;

  const INNER_MI = 10;
  const OUTER_MI = 25;
  const WINDOW_MS = 20 * 60 * 1000;
  const WINDOW_SEC = Math.floor(WINDOW_MS / 1000);
  const KM_PER_MI = 1.609344;
  const OUTER_KM = OUTER_MI * KM_PER_MI;

  const LTG_GEOJSON_DEFAULT = "https://radar.moonriverweather.com/lightning_points_xweather_local.geojson";

  /** Timestamp (ms) of the most recent ≤10 mi strike we've observed; drives 20 min red hold */
  let lastInnerStrikeAtMs = 0;
  let lastLtgOk = false;

  function $(id) {
    return document.getElementById(id);
  }

  function mrw15(s) {
    if (s === undefined || s === null) return "";
    s = String(s).trim();
    if (!s) return "";
    if (s.length <= MAX_CH) return s;
    return s.slice(0, MAX_CH).trim();
  }

  function setTextSticky(id, v) {
    const el = $(id);
    if (!el) return;
    if (v === undefined || v === null) return;
    const t = String(v);
    if (!t || t === "null" || t === "undefined") return;
    el.textContent = t;
  }

  async function fetchJSON(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return await r.json();
  }

  async function fetchLightningGeoJSON() {
    const url =
      (typeof window !== "undefined" && window.A9P_LIGHTNING_GEOJSON_URL) ||
      LTG_GEOJSON_DEFAULT;
    const r = await fetch(url, { cache: "no-store", credentials: "omit" });
    if (!r.ok) throw new Error("ltg " + r.status);
    return await r.json();
  }

  function num(v) {
    return typeof v === "number" && !isNaN(v) ? v : undefined;
  }

  function setDotColor(dotEl, token) {
    if (!dotEl) return;
    const c = (token || "NONE").toString().trim().toUpperCase();
    let bg = "transparent";
    if (["RED", "WARNING", "ALERT", "DANGER"].includes(c)) bg = "#dc2626";
    if (["YELLOW", "WATCH", "CAUTION", "ORANGE", "ADVISORY"].includes(c)) bg = "#f0b429";
    if (["GRAY", "GREY", "INFO", "UNKNOWN"].includes(c)) bg = "#6b7280";
    if (["GREEN", "OK", "GOOD", "LIVE", "HEALTHY", "CLEAR"].includes(c)) bg = "#16a34a";
    dotEl.style.backgroundColor = bg;
    dotEl.style.background = bg;
  }

  function threatTextLevel(threatStr) {
    const t = (threatStr || "").toString().toLowerCase();
    if (!t) return "";
    if (/\bwarning\b/.test(t) || /\bemergency\b/.test(t)) return "WARNING";
    if (/\bwatch\b/.test(t)) return "WATCH";
    return "";
  }

  function effectiveNwsLevel(nws) {
    const fromText = threatTextLevel((nws && nws.threat) ? nws.threat : "");
    if (fromText) return fromText;
    const lvl = (nws && nws.level ? String(nws.level).trim().toUpperCase() : "");
    if (lvl === "WARNING" || lvl === "WATCH" || lvl === "ADVISORY") return lvl;
    return lvl || "NONE";
  }

  function mrwDotForLocal(localStr) {
    const s = (localStr || "").toString().toUpperCase();
    if (!s || s.includes("MRW: CLEAR")) return "NONE";
    if (s.includes("AIR LIMIT")) return "YELLOW";
    if (s.includes("WIND")) return "YELLOW";
    if (s.includes("RAIN")) return "YELLOW";
    if (s.includes("HEAT")) return "YELLOW";
    if (s.includes("COLD")) return "GRAY";
    return "GRAY";
  }

  function nwsDotToken(nws) {
    const lvl = effectiveNwsLevel(nws);
    if (lvl === "WARNING") return "RED";
    if (lvl === "WATCH") return "YELLOW";
    if (lvl === "ADVISORY") return "YELLOW";
    const color = (nws && nws.color ? String(nws.color).trim().toUpperCase() : "");
    if (color) {
      const threatLow = ((nws && nws.threat) || "").toString().toLowerCase();
      if (/\bwatch\b/.test(threatLow) && !/\bwarning\b/.test(threatLow)) return "YELLOW";
      return color;
    }
    return "NONE";
  }

  function overallFrom(nws, mrwLocal) {
    const lvl = effectiveNwsLevel(nws || {});
    const local = (mrwLocal || "").toString().toUpperCase();
    if (lvl === "WARNING") return { txt: "ALERT", dot: "RED" };
    if (lvl === "WATCH") return { txt: "CAUTION", dot: "YELLOW" };
    if (lvl === "ADVISORY") return { txt: "CAUTION", dot: "YELLOW" };
    if (local && !local.includes("MRW: CLEAR")) return { txt: "CAUTION", dot: mrwDotForLocal(local) || "GRAY" };
    return { txt: "CLEAR", dot: "NONE" };
  }

  function applyLtgTextClass(el, mode) {
    if (!el) return;
    el.classList.remove("a9ThreatText--ltgYellow", "a9ThreatText--ltgClose");
    if (mode === "yellow") el.classList.add("a9ThreatText--ltgYellow");
    if (mode === "close") el.classList.add("a9ThreatText--ltgClose");
  }

  /**
   * Scans Xweather GeoJSON: strikes ≤25 mi and ≤20 min old.
   * Updates lastInnerStrikeAtMs when any ≤10 mi strike is present.
   * Returns display mode: 'close' | 'yellow' | 'none'
   */
  function computeLtgMode(ltgJson, nowMs) {
    const features = (ltgJson && ltgJson.features) || [];
    let hasInnerRecent = false;
    let hasOuterRecent = false;
    let hasAny25Recent = false;
    let minInnerAgeSec = Infinity;

    for (let i = 0; i < features.length; i++) {
      const p = (features[i] && features[i].properties) || {};
      const distKm = num(p.distance_km);
      const ageSec = num(p.age_seconds);
      if (distKm == null || ageSec == null) continue;
      if (ageSec > WINDOW_SEC) continue;
      if (distKm > OUTER_KM) continue;

      const distMi = distKm / KM_PER_MI;
      hasAny25Recent = true;

      if (distMi <= INNER_MI) {
        hasInnerRecent = true;
        if (ageSec < minInnerAgeSec) minInnerAgeSec = ageSec;
      } else if (distMi <= OUTER_MI) {
        hasOuterRecent = true;
      }
    }

    if (hasInnerRecent && minInnerAgeSec < Infinity) {
      const strikeMs = nowMs - minInnerAgeSec * 1000;
      if (strikeMs > lastInnerStrikeAtMs) lastInnerStrikeAtMs = strikeMs;
    }

    const holdActive =
      lastInnerStrikeAtMs > 0 && nowMs - lastInnerStrikeAtMs < WINDOW_MS;

    if (hasInnerRecent || holdActive) {
      return "close";
    }

    if (hasOuterRecent) {
      return "yellow";
    }

    if (!hasAny25Recent) {
      lastInnerStrikeAtMs = 0;
      return "none";
    }

    lastInnerStrikeAtMs = 0;
    return "none";
  }

  function renderLtgRow(mode) {
    const txtEl = $("tr_ltg_txt");
    const dotEl = $("tr_ltg_dot");
    if (mode === "close") {
      setTextSticky("tr_ltg_txt", mrw15("Lightning CLOSE"));
      setDotColor(dotEl, "RED");
      applyLtgTextClass(txtEl, "close");
    } else if (mode === "yellow") {
      setTextSticky("tr_ltg_txt", mrw15("Lightning 10-25"));
      setDotColor(dotEl, "YELLOW");
      applyLtgTextClass(txtEl, "yellow");
    } else {
      setTextSticky("tr_ltg_txt", mrw15("NO LIGHTNING"));
      setDotColor(dotEl, "NONE");
      applyLtgTextClass(txtEl, "none");
    }
  }

  async function poll() {
    let tj;
    let ltgJson = null;
    try {
      tj = await fetchJSON("/data/threat_strip.json?ts=" + Date.now());
    } catch (e) {
      return;
    }

    try {
      ltgJson = await fetchLightningGeoJSON();
      lastLtgOk = true;
    } catch (e) {
      if (!lastLtgOk) {
        /* first loads failing — leave LTG placeholder */
      }
      /* sticky LTG on transient errors */
    }

    const nws = tj.nws || {};
    const local = (tj.local || "").toString().toUpperCase();

    const nwsThreat = ((nws.threat || "") + "").toUpperCase();
    const nwsTxt = mrw15(nwsThreat ? nwsThreat : "NONE");
    setTextSticky("tr_nws_txt", nwsTxt);
    setDotColor($("tr_nws_dot"), nwsDotToken(nws));

    const _mrwRaw = local ? local : "MRW: CLEAR";
    const _mrwClean = _mrwRaw.replace(/^\s*MRW\s*:\s*/i, "").replace(/^\s*MRW\s+/i, "").trim();
    const mrwTxt = mrw15(_mrwClean || "CLEAR");
    setTextSticky("tr_mrw_txt", mrwTxt);
    setDotColor($("tr_mrw_dot"), mrwDotForLocal(local));

    const ov = overallFrom(nws, local);
    setTextSticky("tr_overall_txt", mrw15(ov.txt));
    setDotColor($("tr_overall_dot"), ov.dot);

    if (ltgJson) {
      const mode = computeLtgMode(ltgJson, Date.now());
      renderLtgRow(mode);
    }
  }

  setInterval(poll, POLL_MS);
  poll();
})();
