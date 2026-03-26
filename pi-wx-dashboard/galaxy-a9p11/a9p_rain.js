/* A9P_RIGHT1_RAIN_JS_V1 — render-only wiring (Galaxy14 sources/keys) */
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
      const d = await fetchJSON("/data/rain.json?ts=" + Date.now());
      const x = (d && d.rain) ? d.rain : {};

      // Galaxy14 keys
      const today = fmt2(x.today_in);
      const rate  = fmt2(x.rate_inhr);
      const storm = fmt2(x.storm_in);

      if (today != null) setTextSticky("a9_rain_today", today);
      if (rate  != null) setTextSticky("a9_rain_rate",  rate);
      if (storm != null) setTextSticky("a9_rain_storm", storm);

      const k = await fetchJSON("/data/computed_rt.json?ts=" + Date.now());
      const cc2 = (k && k.computed) ? k.computed : {};
      if (cc2.rain_days_since_stop != null) setTextSticky("a9_rain_days", Math.round(cc2.rain_days_since_stop));
    }catch(e){
      // sticky
    }
  }

  setInterval(poll, POLL_MS);
  poll();
})();
