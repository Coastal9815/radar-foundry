/* A9P_RIGHT2_RAINACC_JS_V2 — Month/Year inches + % of norm aligned with Master rain-accumulation.js */
(function(){
  const POLL_MS = 2500;

  const DEFAULT_MONTH_NORMS_IN = [3.28, 2.80, 3.50, 3.39, 3.62, 6.65, 5.75, 5.46, 4.35, 3.72, 2.39, 3.21];
  const DEFAULT_YEAR_NORM_IN = 48.12;

  function $(id){ return document.getElementById(id); }
  function setTextSticky(id, v){
    const el = $(id);
    if (!el) return;
    if (v === undefined || v === null) return;
    const t = String(v);
    if (!t || t === "null" || t === "undefined") return;
    el.textContent = t;
  }
  function num(x){
    if (x === undefined || x === null) return null;
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
  }
  function fmt2(x){
    const n = num(x);
    return (n == null) ? null : n.toFixed(2);
  }
  async function fetchJSON(url){
    const r = await fetch(url, {cache:"no-store"});
    if (!r.ok) throw new Error(url + " " + r.status);
    return await r.json();
  }

  async function poll(){
    try{
      const r = await fetchJSON("/data/rain.json?ts=" + Date.now());
      const rain = (r && r.rain) ? r.rain : {};
      const m_in = fmt2(rain.month_in);
      const y_in = fmt2(rain.year_in);
      if (m_in != null) setTextSticky("a9_m_rain", m_in);
      if (y_in != null) setTextSticky("a9_y_rain", y_in);

      const monthIn = Number(rain.month_in ?? rain.month_rain_in ?? 0);
      const yearIn = Number(rain.year_in ?? rain.year_rain_in ?? 0);

      let norms = null;
      try {
        const nr = await fetch("/data/rain_norms.json?ts=" + Date.now(), { cache: "no-store" });
        if (nr.ok) norms = await nr.json();
      } catch (_) { /* defaults */ }

      const monthNorms = (norms && Array.isArray(norms.month_norm_in))
        ? norms.month_norm_in : DEFAULT_MONTH_NORMS_IN;
      const yearNorm = num(norms?.year_norm_in) ?? DEFAULT_YEAR_NORM_IN;

      const tz = "America/New_York";
      const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" });
      const parts = Object.fromEntries(fmt.formatToParts(new Date()).map((p) => [p.type, p.value]));
      const year = parseInt(parts.year, 10);
      const monthIdx = parseInt(parts.month, 10) - 1;
      const monthNorm = monthNorms[monthIdx];
      const daysElapsed = parseInt(parts.day, 10);
      const daysInMonth = new Date(year, monthIdx + 1, 0).getDate();

      let expectedToDate = 0;
      for (let m = 0; m < monthIdx; m++) expectedToDate += Number(monthNorms[m]) || 0;
      expectedToDate += (monthNorm > 0 && daysInMonth > 0)
        ? (monthNorm / daysInMonth) * daysElapsed : 0;
      expectedToDate = expectedToDate > 0 ? expectedToDate : null;

      const expectedMonthToDate = (monthNorm > 0 && daysInMonth > 0)
        ? (monthNorm / daysInMonth) * daysElapsed : null;
      const monthPct = (expectedMonthToDate != null && expectedMonthToDate > 0 && Number.isFinite(monthIn))
        ? (monthIn / expectedMonthToDate) * 100 : null;
      const yearPct = (expectedToDate != null && expectedToDate > 0 && Number.isFinite(yearIn))
        ? (yearIn / expectedToDate) * 100 : null;

      if (monthPct != null && Number.isFinite(monthPct)) setTextSticky("a9_m_norm", Math.round(monthPct));
      if (yearPct != null && Number.isFinite(yearPct)) setTextSticky("a9_y_norm", Math.round(yearPct));
    }catch(e){
      // sticky
    }
  }

  setInterval(poll, POLL_MS);
  poll();
})();
