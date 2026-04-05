/* A9P_RIGHT3_THREAT_JS_V1 — render-only wiring for Threat/Conditions */
(function(){
  const POLL_MS = 2500;
  const MAX_CH = 15; // global NWS/MRW alert text cap (incl spaces)

  function $(id){ return document.getElementById(id); }

  function mrw15(s){
    if (s === undefined || s === null) return "";
    s = String(s).trim();
    if (!s) return "";
    if (s.length <= MAX_CH) return s;
    return s.slice(0, MAX_CH).trim();
  }

  function setTextSticky(id, v){
    const el = $(id);
    if (!el) return;
    if (v === undefined || v === null) return;
    const t = String(v);
    if (!t || t === "null" || t === "undefined") return;
    el.textContent = t;
  }

  async function fetchJSON(url){
    const r = await fetch(url, {cache:"no-store"});
    if (!r.ok) throw new Error(url + " " + r.status);
    return await r.json();
  }
  function setDotColor(dotEl, token){
    if (!dotEl) return;
    const c = (token || "NONE").toString().trim().toUpperCase();

    // Robust token mapping:
    // - Accept both "color tokens" (RED/YELLOW/GRAY/GREEN) and "level tokens" (WARNING/WATCH/ADVISORY)
    // - Default to transparent for NONE/EMPTY
    let bg = "transparent";

    // RED family
    if (["RED","WARNING","ALERT","DANGER"].includes(c)) bg = "#dc2626";

    // YELLOW family (treat Advisory as CAUTION per A9 intent)
    if (["YELLOW","WATCH","CAUTION","ORANGE","ADVISORY"].includes(c)) bg = "#f0b429";

    // GRAY family (reserved / informational)
    if (["GRAY","GREY","INFO","UNKNOWN"].includes(c)) bg = "#6b7280";

    // GREEN family (healthy)
    if (["GREEN","OK","GOOD","LIVE","HEALTHY","CLEAR"].includes(c)) bg = "#16a34a";

    // Apply both (some CSS uses background-color)
    dotEl.style.backgroundColor = bg;
    dotEl.style.background = bg;
  }

  /** WATCH never maps to RED: prefer headline words over upstream level/color mismatches. */
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

  function mrwDotForLocal(localStr){
    // localStr format: "MRW: CLEAR" or "MRW: AIR LIMIT/WIND" etc
    const s = (localStr || "").toString().toUpperCase();
    if (!s || s.includes("MRW: CLEAR")) return "NONE";
    // simple severity heuristic (render-only; truth decides items)
    if (s.includes("AIR LIMIT")) return "YELLOW";
    if (s.includes("WIND")) return "YELLOW";
    if (s.includes("RAIN")) return "YELLOW";
    if (s.includes("HEAT")) return "YELLOW";
    if (s.includes("COLD")) return "GRAY";
    return "GRAY";
  }
  function nwsDotToken(nws){
    const lvl = effectiveNwsLevel(nws);
    if (lvl === "WARNING") return "RED";
    if (lvl === "WATCH") return "YELLOW";
    if (lvl === "ADVISORY") return "YELLOW";

    const color = (nws && nws.color ? String(nws.color).trim().toUpperCase() : "");
    if (color) {
      if (/\bwatch\b/.test(((nws && nws.threat) || "").toString().toLowerCase()) &&
          !/\bwarning\b/.test(((nws && nws.threat) || "").toString().toLowerCase())) {
        return "YELLOW";
      }
      return color;
    }
    return "NONE";
  }
  function overallFrom(nws, mrwLocal){
    const lvl = effectiveNwsLevel(nws || {});
    const local = (mrwLocal || "").toString().toUpperCase();

    if (lvl === "WARNING") return { txt: "ALERT", dot: "RED" };
    if (lvl === "WATCH")   return { txt: "CAUTION", dot: "YELLOW" };
    if (lvl === "ADVISORY")return { txt: "CAUTION", dot: "YELLOW" };

    if (local && !local.includes("MRW: CLEAR")) return { txt: "CAUTION", dot: mrwDotForLocal(local) || "GRAY" };

    return { txt: "CLEAR", dot: "NONE" };
  }

  async function poll(){
    try{
      const tj = await fetchJSON("/data/threat_strip.json?ts=" + Date.now());
      if (!tj) return;

      const nws = tj.nws || {};
      const local = (tj.local || "").toString().toUpperCase();

      // Row 2: NWS
      const nwsThreat = ((nws.threat || "") + "").toUpperCase();
      const nwsTxt = mrw15(nwsThreat ? nwsThreat : "NONE");
      setTextSticky("tr_nws_txt", nwsTxt);
      setDotColor($("tr_nws_dot"), nwsDotToken(nws));// Row 3: MRW
      const _mrwRaw = (local ? local : "MRW: CLEAR");
      const _mrwClean = _mrwRaw.replace(/^\s*MRW\s*:\s*/i, "").replace(/^\s*MRW\s+/i, "").trim();
      const mrwTxt = mrw15(_mrwClean || "CLEAR");
      setTextSticky("tr_mrw_txt", mrwTxt);
      setDotColor($("tr_mrw_dot"), mrwDotForLocal(local));

      // Row 1: Overall
      const ov = overallFrom(nws, local);
      setTextSticky("tr_overall_txt", mrw15(ov.txt));
      setDotColor($("tr_overall_dot"), ov.dot);

      // Row 4: Lightning (reserved)
      // Placeholder until lightning feed exists
      setTextSticky("tr_ltg_txt", mrw15("NO LIGHTNING"));
      setDotColor($("tr_ltg_dot"), "NONE");

    }catch(e){
      // sticky by design
    }
  }

  setInterval(poll, POLL_MS);
  poll();
})();
