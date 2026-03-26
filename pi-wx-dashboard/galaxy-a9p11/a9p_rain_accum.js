/* A9P_RIGHT2_RAINACC_JS_V1 — render-only wiring */
(function(){
  const POLL_MS = 2500;

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
      // Month/Year inches
      const r = await fetchJSON("/data/rain.json?ts=" + Date.now());
      const rain = (r && r.rain) ? r.rain : {};
      const m_in = fmt2(rain.month_in);
      const y_in = fmt2(rain.year_in);
      if (m_in != null) setTextSticky("a9_m_rain", m_in);
      if (y_in != null) setTextSticky("a9_y_rain", y_in);

      // % of normal (Month/Year)
      const c = await fetchJSON("/data/climatology.json?ts=" + Date.now());
      const cc = (c && c.computed) ? c.computed : {};
      if (cc.month_pct_of_normal != null)
        setTextSticky("a9_m_norm", Math.round(cc.month_pct_of_normal * 100));
      if (cc.year_pct_of_normal != null)
        setTextSticky("a9_y_norm", Math.round(cc.year_pct_of_normal * 100));
    }catch(e){
      // sticky
    }
  }

  setInterval(poll, POLL_MS);
  poll();
})();
